import time
import uuid
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .config import WEBHOOK_SECRET
from .models import (
    RazorpayDispute, RazorpayPayment, DisputeStatus, DecisionStatus, DisputeSource
)
from .database import (
    save_dispute, save_payment, save_evidence, get_dispute, get_payment,
    append_audit_event, get_evidence
)
from .feature_extractor import extract_features
from .risk_scorer import risk_scorer
from .evidence_agent import evidence_agent
from .decision_gate import decision_gate
from .razorpay_client import razorpay_client
from .webhook import compute_signature

logger = logging.getLogger("disputeguard.simulator")

DEMO_ARCHETYPES = {
    "auto_contest_winnable": {
        "title": "High-Confidence Winnable Dispute (Auto-Contested < ₹2,000)",
        "amount": 1499.0,
        "reason_code": "goods_not_as_described",
        "phase": "chargeback",
        "order_id": "order_winnable_physical_01",
        "method": "card",
        "respond_window_hours": 72.0
    },
    "over_ceiling_escalate": {
        "title": "High-Value Dispute Exceeding ₹2,000 Ceiling (Human Review)",
        "amount": 18500.0,
        "reason_code": "product_not_received",
        "phase": "chargeback",
        "order_id": "order_high_value_05",
        "method": "card",
        "respond_window_hours": 96.0
    },
    "auto_accept_low_roi": {
        "title": "Low-Value Duplicate Dispute (Auto-Accepted)",
        "amount": 450.0,
        "reason_code": "duplicate",
        "phase": "chargeback",
        "order_id": "order_unwinnable_dup_04",
        "method": "upi",
        "respond_window_hours": 48.0
    },
    "no_fabrication_missing_proof": {
        "title": "Missing Proof Case (No-Fabrication Rule Enforced)",
        "amount": 2899.0,
        "reason_code": "product_not_received",
        "phase": "chargeback",
        "order_id": "order_missing_shipping_03",
        "method": "card",
        "respond_window_hours": 48.0
    },
    "induced_upload_failure": {
        "title": "Induced Upload 503 Timeout (§4.3 Graceful Escalation)",
        "amount": 3200.0,
        "reason_code": "goods_not_as_described",
        "phase": "chargeback",
        "order_id": "order_winnable_physical_01",
        "method": "card",
        "respond_window_hours": 72.0
    }
}

def seed_simulated_dispute(archetype_key: str = "auto_contest_winnable", induce_failure: bool = False) -> Dict[str, Any]:
    """
    Seeds a synthetic dispute record matching genuine Razorpay test entities,
    triggers HMAC-signed webhook simulation and launches the full pipeline.
    """
    archetype = DEMO_ARCHETYPES.get(archetype_key, DEMO_ARCHETYPES["auto_contest_winnable"])
    unique_suffix = uuid.uuid4().hex[:6]
    dispute_id = f"disp_{archetype_key[:10]}_{unique_suffix}"
    payment_id = f"pay_{unique_suffix}"

    now = int(time.time())
    respond_by = int(now + archetype["respond_window_hours"] * 3600)

    # 1. Create entities
    dispute = RazorpayDispute(
        id=dispute_id,
        payment_id=payment_id,
        amount=archetype["amount"],
        currency="INR",
        amount_deducted=archetype["amount"],
        reason_code=archetype["reason_code"],
        phase=archetype["phase"],
        respond_by=respond_by,
        status=DisputeStatus.OPEN,
        decision_status=DecisionStatus.PENDING_SCORING,
        source=DisputeSource.SIMULATED,
        created_at=now
    )
    save_dispute(dispute)

    payment = RazorpayPayment(
        id=payment_id,
        order_id=archetype["order_id"],
        amount=archetype["amount"],
        currency="INR",
        method=archetype["method"],
        email=f"customer.{unique_suffix}@example.com",
        contact="+919876543210",
        created_at=now - 86400 * 4
    )
    save_payment(payment)

    # 2. Simulate raw inbound Razorpay webhook payload
    webhook_payload = {
        "entity": "event",
        "account_id": "acc_test_razorpay_merchant",
        "event": "payment.dispute.created",
        "contains": ["dispute", "payment"],
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute.id,
                    "payment_id": payment.id,
                    "amount": int(dispute.amount * 100),  # paise
                    "currency": dispute.currency,
                    "reason_code": dispute.reason_code,
                    "phase": dispute.phase,
                    "status": "open",
                    "respond_by": dispute.respond_by,
                    "created_at": dispute.created_at,
                    "source": "simulated"
                }
            },
            "payment": {
                "entity": {
                    "id": payment.id,
                    "order_id": payment.order_id,
                    "amount": int(payment.amount * 100),
                    "currency": payment.currency,
                    "method": payment.method,
                    "email": payment.email,
                    "contact": payment.contact,
                    "created_at": payment.created_at
                }
            }
        },
        "created_at": now
    }

    raw_body = json.dumps(webhook_payload).encode("utf-8")
    signature = compute_signature(raw_body, WEBHOOK_SECRET)

    # 3. Audit log entry for webhook receipt
    append_audit_event(
        dispute_id=dispute.id,
        event_type="simulated_webhook_dispute_created",
        payload_snapshot={
            "archetype": archetype_key,
            "signature_verified": True,
            "hmac_sha256": signature[:16] + "..."
        },
        actor="dispute_simulator"
    )

    # 4. Execute pipeline synchronously for demo seed
    run_autonomous_pipeline(dispute.id, induce_failure=induce_failure)

    return {
        "dispute_id": dispute.id,
        "payment_id": payment.id,
        "archetype": archetype_key,
        "title": archetype["title"],
        "amount": dispute.amount
    }

def run_autonomous_pipeline(dispute_id: str, induce_failure: bool = False):
    """
    Complete end-to-end DisputeGuard pipeline:
    1. Feature extraction
    2. Evidence packet assembly (No-fabrication rule)
    3. Document uploading with backoff & failure injection
    4. XGBoost risk scoring -> win probability
    5. Bounded Decision Gate evaluation
    6. Action execution & append-only audit trail
    """
    logger.info(f"Starting DisputeGuard pipeline for {dispute_id} (induce_failure={induce_failure})")

    dispute = get_dispute(dispute_id)
    if not dispute:
        logger.error(f"Dispute {dispute_id} not found")
        return

    payment = get_payment(dispute.payment_id)

    # 1. Assemble Evidence Packet (No-Fabrication Rule)
    evidence = evidence_agent.assemble_packet(dispute, payment)

    # 2. Extract Features for ML
    features = extract_features(dispute, payment, evidence)
    append_audit_event(
        dispute_id=dispute.id,
        event_type="features_extracted",
        payload_snapshot=features,
        actor="feature_extractor"
    )

    # 3. Score Win Probability via XGBoost
    win_probability = risk_scorer.predict_win_probability(features)
    append_audit_event(
        dispute_id=dispute.id,
        event_type="risk_scored",
        payload_snapshot={
            "win_probability": win_probability,
            "model": "xgboost_binary_classifier",
            "eval_reference": "held_out_30_stratified"
        },
        actor="risk_scorer"
    )

    # 4. Upload Documents with backoff (or induce failure for §4.3)
    razorpay_client.set_induce_upload_failure(induce_failure)
    upload_success, uploaded_doc_ids, upload_err = evidence_agent.upload_packet_documents(evidence, max_attempts=3)
    # Reset flag after attempt
    razorpay_client.set_induce_upload_failure(False)

    save_evidence(evidence)

    # 5. Evaluate Bounded Decision Gate
    decision = decision_gate.evaluate(
        dispute=dispute,
        win_probability=win_probability,
        evidence=evidence,
        upload_failed=not upload_success
    )

    # 6. Execute Bounded Decision (Auto-contest, auto-accept, or hold for human)
    exec_result = decision_gate.execute_decision(dispute, decision, evidence)

    logger.info(f"Dispute {dispute_id} completed pipeline: action={decision.action}, rule={decision.rule_fired}")
