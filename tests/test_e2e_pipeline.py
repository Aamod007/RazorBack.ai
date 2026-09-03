import time
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import WEBHOOK_SECRET, AMOUNT_CEILING_INR
from backend.app.webhook import compute_signature
from backend.app.database import get_dispute, get_evidence, get_decision, get_audit_events, replay_dispute_events
from backend.app.models import DisputeStatus, DecisionStatus, DecisionAction
from backend.app.simulator import run_autonomous_pipeline

client = TestClient(app)

def test_e2e_pipeline_winnable_auto_contest():
    """
    End-to-end integration test:
    1. Deliver authentic HMAC-signed payment.dispute.created webhook.
    2. Execute full autonomous pipeline (feature extraction -> XGBoost -> evidence upload -> decision gate).
    3. Assert category-mapped documents uploaded to Razorpay API contract.
    4. Assert auto-contest submitted under ₹2,000 ceiling.
    5. Replay immutable audit ledger and verify cryptographic SHA-256 chain integrity.
    """
    now = int(time.time())
    unique_suffix = uuid.uuid4().hex[:6]
    dispute_id = f"disp_e2e_{unique_suffix}"
    payment_id = f"pay_e2e_{unique_suffix}"
    order_id = "order_winnable_physical_01"
    amount_paise = 149900  # ₹1,499.00 (under ₹2,000 ceiling)

    webhook_payload = {
        "entity": "event",
        "account_id": "acc_e2e_test_merchant",
        "event": "payment.dispute.created",
        "contains": ["dispute", "payment"],
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "reason_code": "goods_not_as_described",
                    "phase": "chargeback",
                    "status": "open",
                    "respond_by": now + 86400 * 3,  # 3 days left
                    "created_at": now,
                    "source": "simulated"
                }
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "method": "card",
                    "email": f"customer.{unique_suffix}@example.com",
                    "contact": "+919876543210",
                    "created_at": now - 86400 * 3
                }
            }
        },
        "created_at": now
    }

    body_bytes = json.dumps(webhook_payload).encode("utf-8")
    signature = compute_signature(body_bytes, WEBHOOK_SECRET)

    # 1. Post webhook to API
    response = client.post(
        "/api/webhooks/razorpay",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["dispute_id"] == dispute_id

    # 2. Run pipeline for this dispute
    run_autonomous_pipeline(dispute_id, induce_failure=False)

    # 3. Assert dispute status in DB
    dispute = get_dispute(dispute_id)
    assert dispute is not None
    assert dispute.amount == 1499.0
    assert dispute.status == DisputeStatus.UNDER_REVIEW
    assert dispute.decision_status == DecisionStatus.AUTO_CONTESTED

    # 4. Assert Evidence Packet has proper category mapping
    evidence = get_evidence(dispute_id)
    assert evidence is not None
    assert evidence.upload_status == "success"
    assert len(evidence.uploaded_doc_ids) > 0
    # Must contain slot keys matching Razorpay category schema!
    assert "shipping_proof" in evidence.uploaded_slot_docs
    assert len(evidence.uploaded_slot_docs["shipping_proof"]) > 0

    # 5. Assert Decision Record
    decision = get_decision(dispute_id)
    assert decision is not None
    assert decision.action == DecisionAction.CONTEST_AUTO
    assert decision.rule_fired == "rule_high_confidence_auto_contest"
    assert decision.win_probability >= 0.65

    # 6. Verify Deterministic Event Replay via API
    replay_resp = client.get(f"/api/disputes/{dispute_id}/replay")
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    assert replay_data["integrity_verified"] is True
    assert replay_data["status"] == "verified"
    assert replay_data["events_count"] >= 5
    assert len(replay_data["chain_hash"]) == 64
    assert replay_data["reconstructed_state"]["dispute_id"] == dispute_id
    assert replay_data["reconstructed_state"]["decision_action"] == "contest_auto"
