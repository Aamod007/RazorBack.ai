import pytest
from starlette.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db, save_dispute, save_payment
from backend.app.models import RazorpayDispute, RazorpayPayment, DisputeStatus
from backend.app.evidence_binder import render_evidence_binder_html

@pytest.fixture
def client():
    init_db()
    return TestClient(app)

def test_render_evidence_binder_html():
    """Assert evidence binder HTML renders required legal, financial, and cryptographic sections."""
    dispute = RazorpayDispute(
        id="disp_binder_test_01",
        payment_id="pay_binder_test_01",
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
        id="pay_binder_test_01",
        order_id="order_binder_01",
        amount=1499.0,
        currency="INR",
        status="captured",
        method="card",
        email="test@example.com",
        contact="+919876543210",
        created_at=1725340000
    )
    replay_data = {
        "chain_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
        "timeline": [
            {
                "step": 1,
                "event_type": "dispute_created",
                "actor": "webhook",
                "step_hash": "abc123hash",
                "timestamp": "2026-09-03T12:00:00Z"
            }
        ]
    }

    html = render_evidence_binder_html(
        dispute=dispute,
        payment=payment,
        evidence=None,
        decision=None,
        replay_data=replay_data
    )

    assert "RazorBack" in html
    assert "Bank Submission Evidence" in html
    assert "disp_binder_test_01" in html
    assert "product_not_received" in html
    assert "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0" in html

def test_api_dispute_binder_endpoint(client):
    """Assert GET /api/disputes/{id}/binder returns 200 HTML response."""
    dispute = RazorpayDispute(
        id="disp_binder_api_01",
        payment_id="pay_binder_api_01",
        amount=1850.0,
        currency="INR",
        amount_deducted=1850.0,
        status=DisputeStatus.UNDER_REVIEW,
        reason_code="goods_not_as_described",
        phase="chargeback",
        created_at=1725350000,
        respond_by=1725500000
    )
    payment = RazorpayPayment(
        id="pay_binder_api_01",
        order_id="order_binder_api_01",
        amount=1850.0,
        currency="INR",
        status="captured",
        method="upi",
        email="buyer@example.com",
        contact="+919999999999",
        created_at=1725340000
    )
    save_dispute(dispute)
    save_payment(payment)

    resp = client.get("/api/disputes/disp_binder_api_01/binder")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "RazorBack" in resp.text
    assert "disp_binder_api_01" in resp.text

def test_api_dispute_binder_not_found(client):
    """Assert GET /api/disputes/{id}/binder returns 404 for missing dispute."""
    resp = client.get("/api/disputes/disp_nonexistent/binder")
    assert resp.status_code == 404
