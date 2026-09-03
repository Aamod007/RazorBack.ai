import uuid
import pytest
from backend.app.models import RazorpayDispute, EvidencePacket, DecisionAction, DisputeStatus, DisputeSource
from backend.app.evidence_agent import evidence_agent
from backend.app.decision_gate import decision_gate
from backend.app.razorpay_client import razorpay_client
from backend.app.database import get_audit_events

def test_induced_upload_failure_and_graceful_escalation():
    """
    PRD §4.3: Verify 3x backoff retry on upload 5xx, raw error logging in Audit Log,
    and routing to human escalation (never silent accept).
    """
    dispute_id = f"disp_test_fail_{uuid.uuid4().hex[:6]}"
    dispute = RazorpayDispute(
        id=dispute_id,
        payment_id="pay_test_fail",
        amount=3200.0,
        currency="INR",
        amount_deducted=3200.0,
        reason_code="goods_not_as_described",
        phase="chargeback",
        respond_by=1725000000,
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED,
        created_at=1724000000
    )
    packet = EvidencePacket(
        dispute_id=dispute_id,
        slots={
            "shipping_proof": [{"doc": "test"}],
            "billing_proof": [{"doc": "invoice"}]
        },
        completeness_score=0.85
    )

    # Induce failure in Razorpay upload endpoint
    razorpay_client.set_induce_upload_failure(True)
    
    success, uploaded_doc_ids, err = evidence_agent.upload_packet_documents(packet, max_attempts=3)
    
    # Reset induced failure
    razorpay_client.set_induce_upload_failure(False)

    # Must fail after exactly 3 backoff attempts
    assert success is False
    assert packet.upload_status == "failed"
    assert packet.upload_attempts == 3
    assert "Gateway Timeout" in str(err)

    # Verify Decision Gate handles upload failure
    decision = decision_gate.evaluate(
        dispute=dispute,
        win_probability=0.85,  # High win probability
        evidence=packet,
        upload_failed=True
    )

    # Critical requirement: NEVER auto-accept on technical failure!
    assert decision.action != DecisionAction.ACCEPT
    assert decision.action == DecisionAction.ESCALATE
    assert decision.rule_fired == "rule_upload_failed_graceful_escalate"
    assert "Technical failure is NOT treated as unwinnable" in decision.explanation

    # Verify audit events recorded all 3 failed attempts
    events = get_audit_events(dispute_id)
    fail_events = [e for e in events if e.event_type == "document_upload_attempt_failed"]
    assert len(fail_events) == 3
    for idx, e in enumerate(fail_events, 1):
        assert e.payload_snapshot["attempt"] == idx
        assert "raw_error_details" in e.payload_snapshot
