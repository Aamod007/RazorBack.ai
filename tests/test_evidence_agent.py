import pytest
from backend.app.models import RazorpayDispute, RazorpayPayment, DisputeStatus, DisputeSource
from backend.app.evidence_agent import evidence_agent

def test_evidence_assembly_complete():
    dispute = RazorpayDispute(
        id="disp_test_001",
        payment_id="pay_test_001",
        amount=3499.0,
        currency="INR",
        amount_deducted=3499.0,
        reason_code="product_not_received",
        phase="chargeback",
        respond_by=1725000000,
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED,
        created_at=1724000000
    )
    payment = RazorpayPayment(
        id="pay_test_001",
        order_id="order_winnable_physical_01",
        amount=3499.0,
        currency="INR",
        method="card",
        created_at=1724000000
    )

    packet = evidence_agent.assemble_packet(dispute, payment)

    # All slots exist
    assert "shipping_proof" in packet.slots
    assert "billing_proof" in packet.slots
    assert "explanation_letter" in packet.slots

    # Shipping proof populated with tracking
    assert len(packet.slots["shipping_proof"]) > 0
    assert packet.slots["shipping_proof"][0]["tracking_number"] == "BLUEDART-849204192"

    # Razorpay 1000-character constraint strictly maintained
    letter = packet.slots["explanation_letter"]
    assert len(letter) <= 1000
    assert len(letter) > 50

    # Completeness score should be 1.0 (all required slots for product_not_received present)
    assert packet.completeness_score == 1.0
    assert len(packet.missing_slots) == 0

def test_no_fabrication_rule_enforcement():
    """
    PRD §4.2 #6: Never backfills with invented text or documents.
    Missing carrier tracking must leave slot empty and decrease completeness score.
    """
    dispute = RazorpayDispute(
        id="disp_test_nofab",
        payment_id="pay_test_nofab",
        amount=2899.0,
        currency="INR",
        amount_deducted=2899.0,
        reason_code="product_not_received",
        phase="chargeback",
        respond_by=1725000000,
        status=DisputeStatus.OPEN,
        source=DisputeSource.SIMULATED,
        created_at=1724000000
    )
    payment = RazorpayPayment(
        id="pay_test_nofab",
        order_id="order_missing_shipping_03",  # Order with missing tracking
        amount=2899.0,
        currency="INR",
        method="card",
        created_at=1724000000
    )

    packet = evidence_agent.assemble_packet(dispute, payment)

    # Shipping proof must NOT be fabricated
    assert len(packet.slots["shipping_proof"]) == 0
    assert "shipping_proof" in packet.missing_slots

    # Completeness score must drop accordingly
    assert packet.completeness_score < 1.0
