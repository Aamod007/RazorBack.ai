import pytest
from backend.app.carrier_client import carrier_client, CarrierClient
from backend.app.evidence_agent import evidence_agent
from backend.app.models import RazorpayDispute, RazorpayPayment, DisputeStatus

def test_carrier_client_simulated_telemetry():
    """Verify that carrier client generates realistic delivery proof with digital signature."""
    client = CarrierClient()
    res = client.fetch_tracking_telemetry(awb="BD-998877", carrier="Blue Dart Express")

    assert res["awb"] == "BD-998877"
    assert res["carrier"] == "Blue Dart Express"
    assert res["status"] == "delivered"
    assert res["delivered"] is True
    assert "recipient_signed_by" in res
    assert "delivered_date" in res
    assert "delivered_location" in res

def test_carrier_client_missing_awb():
    """Verify graceful handling when no tracking number is supplied."""
    client = CarrierClient()
    res = client.fetch_tracking_telemetry(awb="")
    assert res["delivered"] is False
    assert res["status"] == "missing_awb"

def test_evidence_agent_integrates_carrier_proof():
    """Verify that evidence agent invokes carrier_client and populates shipping_proof slot."""
    dispute = RazorpayDispute(
        id="disp_carrier_test_01",
        payment_id="pay_carrier_test_01",
        amount=1499.0,
        currency="INR",
        amount_deducted=1499.0,
        status=DisputeStatus.UNDER_REVIEW,
        reason_code="product_not_received",
        phase="chargeback",
        created_at=1725350000,
        respond_by=1725500000
    )
    payment = RazorpayPayment(
        id="pay_carrier_test_01",
        order_id="order_winnable_physical_01",
        amount=1499.0,
        currency="INR",
        status="captured",
        method="upi",
        email="rohan@example.com",
        contact="+919876543210",
        created_at=1725340000
    )

    packet = evidence_agent.assemble_packet(dispute, payment)
    shipping_proofs = packet.slots.get("shipping_proof", [])

    assert len(shipping_proofs) > 0
    proof = shipping_proofs[0]
    assert proof["tracking_number"] == "BLUEDART-849204192"
    assert "Blue Dart" in proof["carrier"]
    assert "recipient_signed_by" in proof
