import pytest
from unittest.mock import patch, MagicMock
from backend.app.alert_bot import AlertBot
from backend.app.models import RazorpayDispute, DisputeStatus
from backend.app.decision_gate import decision_gate
from backend.app.evidence_agent import evidence_agent

@pytest.fixture
def sample_dispute():
    return RazorpayDispute(
        id="disp_alert_test_01",
        payment_id="pay_alert_test_01",
        amount=5000.0,
        currency="INR",
        amount_deducted=5000.0,
        status=DisputeStatus.UNDER_REVIEW,
        reason_code="fraudulent",
        phase="chargeback",
        created_at=1725350000,
        respond_by=1725500000
    )

def test_alert_bot_graceful_when_no_webhook_url(sample_dispute):
    """Assert alert bot safely skips and records audit log when webhook URL is unconfigured."""
    bot = AlertBot(webhook_url="")
    res = bot.notify_high_value_dispute(sample_dispute, win_probability=0.85, rule_fired="rule_amount_ceiling_exceeded")

    assert res["status"] == "skipped"
    assert res["reason"] == "no_webhook_url_configured"

def test_alert_bot_urgent_deadline_formatting(sample_dispute):
    """Assert urgent SLA alert formatting and audit logging."""
    bot = AlertBot(webhook_url="")
    res = bot.notify_urgent_deadline(sample_dispute, hours_remaining=8.5)

    assert res["status"] == "skipped"

def test_alert_bot_dispatches_when_url_provided(sample_dispute):
    """Assert webhook is dispatched when URL is present."""
    bot = AlertBot(webhook_url="https://hooks.slack.com/services/T00/B00/X00")

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        res = bot.notify_high_value_dispute(sample_dispute, win_probability=0.75, rule_fired="rule_amount_ceiling_exceeded")

        assert mock_post.called
        assert res["status"] == "dispatched"
        assert res["status_code"] == 200

import time

def test_decision_gate_triggers_alert_on_high_value(sample_dispute):
    """Assert decision gate triggers alert_bot for disputes > ₹2,000 ceiling."""
    evidence = MagicMock()
    evidence.upload_status = "success"
    evidence.completeness_score = 0.90
    evidence.missing_slots = []
    sample_dispute.respond_by = int(time.time()) + 36 * 3600

    with patch("backend.app.decision_gate.alert_bot.notify_high_value_dispute") as mock_alert:
        decision_gate.evaluate(sample_dispute, win_probability=0.88, evidence=evidence)
        assert mock_alert.called
