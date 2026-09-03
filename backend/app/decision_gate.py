import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from .config import (
    AMOUNT_CEILING_INR,
    AUTO_CONTEST_CONFIDENCE_FLOOR,
    AUTO_CONTEST_MIN_COMPLETENESS,
    AUTO_ACCEPT_THRESHOLD_INR,
    AUTO_ACCEPT_CONFIDENCE_CEILING,
    DEADLINE_URGENT_HOURS,
    DEADLINE_FAILSAFE_HOURS
)
from .models import (
    RazorpayDispute, RazorpayPayment, EvidencePacket,
    DecisionRecord, DecisionAction, DecisionStatus, DisputeStatus
)
from .database import (
    save_decision, update_dispute_status, append_audit_event, get_decision
)
from .razorpay_client import razorpay_client
from .alert_bot import alert_bot

logger = logging.getLogger("disputeguard.decision_gate")

class DecisionGate:
    """
    The only component permitted to trigger money-relevant dispute actions.
    Applies strict, auditable bounded rules in prioritized sequence:

    [Inbound Dispute]
           │
           ▼
    [Rule 0: Upload Failure?] ── Yes ──► [ESCALATE (Never silent accept)]
           │ No
           ▼
    [Rule 1: Amount > Ceiling?] ── Yes ──► [CONTEST_DRAFT (Human Review Queue)]
           │ No (<= ₹2,000)
           ▼
    [Rule 2: Hours <= 12h & Comp >= 0.40?] ── Yes ──► [CONTEST_AUTO (Deadline Failsafe)]
           │ No
           ▼
    [Rule 3: Amount <= ₹500 & WinProb <= 0.25?] ── Yes ──► [ACCEPT (Auto-concede)]
           │ No
           ▼
    [Rule 4: WinProb >= 0.65 & Comp >= 0.70 & Zero Missing?] ── Yes ──► [CONTEST_AUTO]
           │ No
           ▼
    [Rule 5: Default] ──► [CONTEST_DRAFT (Human Review Queue)]
    """

    def evaluate(
        self,
        dispute: RazorpayDispute,
        win_probability: float,
        evidence: EvidencePacket,
        upload_failed: bool = False
    ) -> DecisionRecord:
        now = int(time.time())
        hours_remaining = max(0.0, (dispute.respond_by - now) / 3600.0) if dispute.respond_by > now else 0.0

        # Rule 0: Technical Upload Failure Handling (§4.3)
        # Technical failures MUST NOT trigger silent acceptance or silent submission!
        if upload_failed or evidence.upload_status == "failed":
            action = DecisionAction.ESCALATE
            rule_fired = "rule_upload_failed_graceful_escalate"
            explanation = (
                f"Document upload failed after 3 backoff attempts. Escalated to human review queue. "
                f"Successfully uploaded: {len(evidence.uploaded_doc_ids)} docs. Missing docs: {evidence.missing_slots}. "
                f"Technical failure is NOT treated as unwinnable."
            )
            return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

        # Rule 1: Amount Ceiling (> ₹2,000 strictly requires human sign-off - gates Deadline Failsafe)
        if dispute.amount > AMOUNT_CEILING_INR:
            action = DecisionAction.CONTEST_DRAFT
            rule_fired = "rule_amount_ceiling_exceeded"
            urgency_note = f" URGENT: Only {hours_remaining:.1f}h remaining before SLA deadline!" if hours_remaining <= DEADLINE_FAILSAFE_HOURS else ""
            explanation = (
                f"Dispute amount INR {dispute.amount:.2f} exceeds ceiling (INR {AMOUNT_CEILING_INR:.2f}). "
                f"Strict human review required regardless of model confidence ({win_probability:.2f}).{urgency_note}"
            )
            if hours_remaining <= DEADLINE_FAILSAFE_HOURS:
                alert_bot.notify_urgent_deadline(dispute, hours_remaining)
            else:
                alert_bot.notify_high_value_dispute(dispute, win_probability, rule_fired)
            return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

        # Rule 2: Deadline Failsafe (< 12 hours remaining, auto-submit best draft under ceiling)
        if hours_remaining <= DEADLINE_FAILSAFE_HOURS and evidence.completeness_score >= 0.40:
            action = DecisionAction.CONTEST_AUTO
            rule_fired = "rule_deadline_failsafe"
            explanation = (
                f"Deadline safety net triggered ({hours_remaining:.1f}h remaining <= {DEADLINE_FAILSAFE_HOURS}h threshold, "
                f"amount INR {dispute.amount:.2f} <= {AMOUNT_CEILING_INR:.2f}). "
                f"Auto-submitting best-available draft to prevent default forfeiture."
            )
            alert_bot.notify_urgent_deadline(dispute, hours_remaining)
            return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

        # Rule 3: Auto-Accept for Low-Value, Low-Confidence Disputes
        if dispute.amount <= AUTO_ACCEPT_THRESHOLD_INR and win_probability <= AUTO_ACCEPT_CONFIDENCE_CEILING:
            action = DecisionAction.ACCEPT
            rule_fired = "rule_auto_accept_low_roi"
            explanation = (
                f"Dispute amount (INR {dispute.amount:.2f} <= {AUTO_ACCEPT_THRESHOLD_INR}) and win probability "
                f"({win_probability:.2f} <= {AUTO_ACCEPT_CONFIDENCE_CEILING}) indicate negative contest ROI. Auto-conceding."
            )
            return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

        # Rule 4: High Confidence & Complete Evidence Auto-Contest
        if (
            win_probability >= AUTO_CONTEST_CONFIDENCE_FLOOR
            and evidence.completeness_score >= AUTO_CONTEST_MIN_COMPLETENESS
            and len(evidence.missing_slots) == 0
        ):
            action = DecisionAction.CONTEST_AUTO
            rule_fired = "rule_high_confidence_auto_contest"
            explanation = (
                f"High win probability ({win_probability:.2f} >= {AUTO_CONTEST_CONFIDENCE_FLOOR}) and verified evidence "
                f"completeness ({evidence.completeness_score:.2f} >= {AUTO_CONTEST_MIN_COMPLETENESS}) with zero missing slots."
            )
            return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

        # Rule 5: Default Escalation (Draft & Hold for Human Review Queue)
        action = DecisionAction.CONTEST_DRAFT
        rule_fired = "rule_draft_and_hold_human_review"
        reasons = []
        if win_probability < AUTO_CONTEST_CONFIDENCE_FLOOR:
            reasons.append(f"win probability ({win_probability:.2f}) below auto-floor ({AUTO_CONTEST_CONFIDENCE_FLOOR})")
        if evidence.completeness_score < AUTO_CONTEST_MIN_COMPLETENESS:
            reasons.append(f"evidence completeness ({evidence.completeness_score:.2f}) below requirement ({AUTO_CONTEST_MIN_COMPLETENESS})")
        if evidence.missing_slots:
            reasons.append(f"missing slots: {evidence.missing_slots}")
        
        explanation = f"Routed to human review queue due to: {'; '.join(reasons)}."
        return self._build_record(dispute.id, win_probability, action, rule_fired, explanation)

    def execute_decision(self, dispute: RazorpayDispute, decision: DecisionRecord, evidence: EvidencePacket) -> Dict[str, Any]:
        """
        Executes the bounded decision via Razorpay API and maintains audit trail.
        """
        save_decision(decision)

        # Check existing decision for idempotency
        if dispute.decision_status in (
            DecisionStatus.AUTO_CONTESTED, DecisionStatus.MANUALLY_CONTESTED,
            DecisionStatus.AUTO_ACCEPTED, DecisionStatus.MANUALLY_ACCEPTED
        ):
            logger.info(f"Dispute {dispute.id} already has final decision {dispute.decision_status}. Skipping execution.")
            return {"status": "skipped", "reason": "idempotency_limit_hit"}

        action = decision.action
        actor = decision.actor

        # Format document references matching Razorpay schema
        doc_refs = evidence.uploaded_slot_docs if evidence.uploaded_slot_docs else {
            f"doc_{idx}": doc_id for idx, doc_id in enumerate(evidence.uploaded_doc_ids)
        }

        if action == DecisionAction.ACCEPT:
            # POST /disputes/:id/accept
            res = razorpay_client.accept_dispute(dispute.id)
            new_decision_status = DecisionStatus.AUTO_ACCEPTED if actor == "agent" else DecisionStatus.MANUALLY_ACCEPTED
            update_dispute_status(dispute.id, status=DisputeStatus.CLOSED, decision_status=new_decision_status)

            append_audit_event(
                dispute_id=dispute.id,
                event_type="action_dispute_accepted",
                payload_snapshot={
                    "rule_fired": decision.rule_fired,
                    "explanation": decision.explanation,
                    "razorpay_response": res
                },
                actor=actor
            )
            return {"action": "accepted", "response": res}

        elif action == DecisionAction.CONTEST_AUTO:
            # PATCH /disputes/:id/contest with action=submit
            summary = evidence.slots.get("explanation_letter", "Contesting dispute based on attached merchant records.")
            
            res = razorpay_client.contest_dispute(
                dispute_id=dispute.id,
                summary=summary,
                documents=doc_refs,
                action="submit"
            )
            update_dispute_status(dispute.id, status=DisputeStatus.UNDER_REVIEW, decision_status=DecisionStatus.AUTO_CONTESTED)

            append_audit_event(
                dispute_id=dispute.id,
                event_type="action_dispute_contested_auto",
                payload_snapshot={
                    "rule_fired": decision.rule_fired,
                    "documents_attached": len(evidence.uploaded_doc_ids),
                    "razorpay_response": res
                },
                actor=actor
            )
            return {"action": "contested_auto", "response": res}

        elif action == DecisionAction.CONTEST_DRAFT:
            # Save draft via PATCH /disputes/:id/contest without action=submit
            summary = evidence.slots.get("explanation_letter", "")
            res = razorpay_client.contest_dispute(
                dispute_id=dispute.id,
                summary=summary,
                documents=doc_refs,
                action="draft"
            )
            update_dispute_status(dispute.id, status=DisputeStatus.OPEN, decision_status=DecisionStatus.DRAFT_PENDING_REVIEW)

            append_audit_event(
                dispute_id=dispute.id,
                event_type="action_draft_created_held_for_review",
                payload_snapshot={
                    "rule_fired": decision.rule_fired,
                    "explanation": decision.explanation,
                    "summary_len": len(summary)
                },
                actor=actor
            )
            return {"action": "draft_pending_review", "response": res}

        elif action == DecisionAction.ESCALATE:
            update_dispute_status(dispute.id, status=DisputeStatus.ACTION_REQUIRED, decision_status=DecisionStatus.UPLOAD_FAILED_REVIEW)
            append_audit_event(
                dispute_id=dispute.id,
                event_type="action_escalated_to_human_queue",
                payload_snapshot={
                    "rule_fired": decision.rule_fired,
                    "explanation": decision.explanation
                },
                actor=actor
            )
            return {"action": "escalated", "reason": decision.rule_fired}

        return {"status": "unknown_action"}

    def _build_record(self, dispute_id: str, win_probability: float, action: DecisionAction, rule_fired: str, explanation: str) -> DecisionRecord:
        return DecisionRecord(
            dispute_id=dispute_id,
            win_probability=win_probability,
            action=action,
            rule_fired=rule_fired,
            actor="agent",
            timestamp=datetime.now(timezone.utc).isoformat(),
            explanation=explanation
        )

# Global decision gate singleton
decision_gate = DecisionGate()
