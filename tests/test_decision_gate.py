import time
import pytest
from backend.app.models import (
    RazorpayDispute, EvidencePacket, DecisionAction, DisputeStatus, DisputeSource
)
from backend.app.decision_gate import decision_gate

def test_rule_amount_ceiling_exceeded():
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_ceil", payment_id="pay_ceil",
        amount=2500.0,  # > ₹2,000 ceiling
        currency="INR", amount_deducted=2500.0,
        reason_code="product_not_received", phase="chargeback",
        respond_by=now + 86400 * 3, status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now
    )
    evidence = EvidencePacket(dispute_id="disp_ceil", slots={}, completeness_score=1.0)
    
    # Even with 95% win probability, ceiling forces human review!
    decision = decision_gate.evaluate(dispute, win_probability=0.95, evidence=evidence)
    assert decision.action == DecisionAction.CONTEST_DRAFT
    assert decision.rule_fired == "rule_amount_ceiling_exceeded"

def test_rule_high_confidence_auto_contest():
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_auto", payment_id="pay_auto",
        amount=1500.0,  # < ₹2,000 ceiling
        currency="INR", amount_deducted=1500.0,
        reason_code="goods_not_as_described", phase="chargeback",
        respond_by=now + 86400 * 3, status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now
    )
    evidence = EvidencePacket(dispute_id="disp_auto", slots={}, completeness_score=0.90, missing_slots=[])
    
    decision = decision_gate.evaluate(dispute, win_probability=0.82, evidence=evidence)
    assert decision.action == DecisionAction.CONTEST_AUTO
    assert decision.rule_fired == "rule_high_confidence_auto_contest"

def test_rule_auto_accept_low_roi():
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_accept", payment_id="pay_accept",
        amount=350.0,  # <= ₹500
        currency="INR", amount_deducted=350.0,
        reason_code="duplicate", phase="chargeback",
        respond_by=now + 86400 * 2, status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now
    )
    evidence = EvidencePacket(dispute_id="disp_accept", slots={}, completeness_score=0.30)
    
    decision = decision_gate.evaluate(dispute, win_probability=0.15, evidence=evidence)
    assert decision.action == DecisionAction.ACCEPT
    assert decision.rule_fired == "rule_auto_accept_low_roi"

def test_rule_draft_and_hold_human_review():
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_hold", payment_id="pay_hold",
        amount=1800.0,  # < ₹2,000 ceiling
        currency="INR", amount_deducted=1800.0,
        reason_code="fraudulent", phase="chargeback",
        respond_by=now + 86400 * 3, status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now
    )
    # Low completeness / missing slot
    evidence = EvidencePacket(dispute_id="disp_hold", slots={}, completeness_score=0.50, missing_slots=["shipping_proof"])
    
    decision = decision_gate.evaluate(dispute, win_probability=0.70, evidence=evidence)
    assert decision.action == DecisionAction.CONTEST_DRAFT
    assert decision.rule_fired == "rule_draft_and_hold_human_review"

def test_rule_deadline_failsafe():
    now = int(time.time())
    dispute = RazorpayDispute(
        id="disp_failsafe", payment_id="pay_failsafe",
        amount=1750.0,  # < ₹2,000 ceiling
        currency="INR", amount_deducted=1750.0,
        reason_code="product_not_received", phase="chargeback",
        respond_by=now + 3600 * 8,  # Only 8 hours left (< 12 hours)
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now - 86400 * 3
    )
    evidence = EvidencePacket(dispute_id="disp_failsafe", slots={}, completeness_score=0.80)
    
    decision = decision_gate.evaluate(dispute, win_probability=0.55, evidence=evidence)
    assert decision.action == DecisionAction.CONTEST_AUTO
    assert decision.rule_fired == "rule_deadline_failsafe"

def test_high_value_dispute_near_deadline_never_autocontests():
    """
    Critical Architecture Boundary (§4.2 Decision Gate):
    A dispute exceeding the ₹2,000 ceiling must NEVER auto-contest,
    even if it has < 12 hours remaining before SLA expiration.
    """
    now = int(time.time())
    high_val_dispute = RazorpayDispute(
        id="disp_urgent_high_val", payment_id="pay_urgent",
        amount=18500.0,  # Far above ₹2,000 ceiling
        currency="INR", amount_deducted=18500.0,
        reason_code="product_not_received", phase="chargeback",
        respond_by=now + 3600 * 4,  # Only 4 hours left!
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED, created_at=now - 86400 * 4
    )
    complete_evidence = EvidencePacket(
        dispute_id="disp_urgent_high_val",
        slots={"shipping_proof": [{"doc": "pod.pdf"}], "billing_proof": [{"doc": "inv.pdf"}]},
        completeness_score=1.0,
        missing_slots=[]
    )
    
    # Evaluate with 90% win probability and complete evidence
    decision = decision_gate.evaluate(high_val_dispute, win_probability=0.90, evidence=complete_evidence)
    
    # MUST route to human review queue, NEVER auto-contest!
    assert decision.action != DecisionAction.CONTEST_AUTO
    assert decision.action == DecisionAction.CONTEST_DRAFT
    assert decision.rule_fired == "rule_amount_ceiling_exceeded"
    assert "URGENT" in decision.explanation
    assert "Strict human review required" in decision.explanation
