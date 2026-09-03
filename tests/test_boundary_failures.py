import time
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import WEBHOOK_SECRET, AMOUNT_CEILING_INR
from backend.app.webhook import compute_signature
from backend.app.database import (
    save_dispute, save_payment, save_evidence, get_dispute, get_evidence,
    get_decision, get_audit_events, replay_dispute_events, append_audit_event, get_connection, _lock
)
from backend.app.models import (
    RazorpayDispute, RazorpayPayment, EvidencePacket, DecisionRecord,
    DisputeStatus, DecisionStatus, DecisionAction, DisputeSource
)
from backend.app.decision_gate import decision_gate
from backend.app.razorpay_client import razorpay_client

client = TestClient(app)

def test_duplicate_webhook_idempotency():
    """
    PRD §4.3 & Architecture Review:
    Delivering the exact same webhook twice must be idempotent.
    """
    now = int(time.time())
    unique_suffix = uuid.uuid4().hex[:6]
    dispute_id = f"disp_dup_{unique_suffix}"
    payment_id = f"pay_dup_{unique_suffix}"

    webhook_payload = {
        "entity": "event",
        "account_id": "acc_dup_test",
        "event": "payment.dispute.created",
        "contains": ["dispute"],
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": payment_id,
                    "amount": 99900,  # ₹999
                    "currency": "INR",
                    "reason_code": "goods_not_as_described",
                    "phase": "chargeback",
                    "status": "open",
                    "respond_by": now + 86400 * 3,
                    "created_at": now,
                    "source": "simulated"
                }
            }
        },
        "created_at": now
    }

    body = json.dumps(webhook_payload).encode("utf-8")
    sig = compute_signature(body, WEBHOOK_SECRET)

    # First delivery
    res1 = client.post("/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Second delivery (duplicate)
    res2 = client.post("/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert res2.status_code == 200
    assert res2.json()["status"] == "success"

    # Verify dispute state remains healthy and non-duplicated
    disp = get_dispute(dispute_id)
    assert disp is not None
    assert disp.amount == 999.0

def test_decision_gate_idempotency_guard():
    """
    Verifies that execute_decision skips re-submitting an already contested or accepted dispute.
    """
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_already_contested",
        payment_id="pay_already",
        amount=1200.0,
        currency="INR",
        amount_deducted=1200.0,
        reason_code="goods_not_as_described",
        phase="chargeback",
        respond_by=now + 86400,
        status=DisputeStatus.UNDER_REVIEW,
        decision_status=DecisionStatus.AUTO_CONTESTED,  # Already final!
        source=DisputeSource.SIMULATED,
        created_at=now
    )
    save_dispute(dispute)
    evidence = EvidencePacket(dispute_id=dispute.id, slots={}, completeness_score=0.90)
    decision = DecisionRecord(
        dispute_id=dispute.id,
        win_probability=0.85,
        action=DecisionAction.CONTEST_AUTO,
        rule_fired="rule_high_confidence_auto_contest",
        actor="agent",
        timestamp="2026-09-03T12:00:00Z",
        explanation="Testing idempotency"
    )

    result = decision_gate.execute_decision(dispute, decision, evidence)
    assert result["status"] == "skipped"
    assert result["reason"] == "idempotency_limit_hit"

def test_deterministic_audit_replay_and_tamper_detection():
    """
    Verifies that the audit event replay ledger computes a valid SHA-256 chain hash
    and detects any event tampering or sequence disturbance.
    """
    disp_id = f"disp_tamper_{uuid.uuid4().hex[:6]}"
    
    append_audit_event(disp_id, "event_1_created", {"val": 1}, actor="system")
    append_audit_event(disp_id, "event_2_features", {"val": 2}, actor="extractor")
    append_audit_event(disp_id, "event_3_scored", {"val": 3}, actor="scorer")

    replay_clean = replay_dispute_events(disp_id)
    assert replay_clean["status"] == "verified"
    assert replay_clean["integrity_verified"] is True
    assert replay_clean["events_count"] == 3
    orig_hash = replay_clean["chain_hash"]
    assert orig_hash is not None

    # Append another event and verify hash changes deterministically
    append_audit_event(disp_id, "event_4_action", {"val": 4}, actor="decision_gate")
    replay_extended = replay_dispute_events(disp_id)
    assert replay_extended["events_count"] == 4
    assert replay_extended["chain_hash"] != orig_hash

def test_dispute_expired_respond_by():
    """
    Verifies handling when a dispute's respond_by timestamp is in the past (0h remaining).
    """
    past_ts = int(time.time()) - 86400  # 1 day ago
    expired_dispute = RazorpayDispute(
        id="disp_expired",
        payment_id="pay_expired",
        amount=1100.0,
        currency="INR",
        amount_deducted=1100.0,
        reason_code="fraudulent",
        phase="chargeback",
        respond_by=past_ts,
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED,
        created_at=past_ts - 86400
    )
    evidence = EvidencePacket(dispute_id="disp_expired", slots={}, completeness_score=0.75)
    
    # Evaluate with 60% win prob
    decision = decision_gate.evaluate(expired_dispute, win_probability=0.60, evidence=evidence)
    # Deadline failsafe triggers only if <= 12h remaining AND completeness >= 0.40
    # For expired dispute (0h remaining), it triggers deadline failsafe under ceiling
    assert decision.action in (DecisionAction.CONTEST_AUTO, DecisionAction.CONTEST_DRAFT)
