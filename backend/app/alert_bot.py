import logging
import json
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .config import SLACK_WEBHOOK_URL, AMOUNT_CEILING_INR
from .database import append_audit_event
from .models import RazorpayDispute

logger = logging.getLogger("razorback.alerts")

class AlertBot:
    """
    Real-Time SLA & Escalation Alert Bot for RazorBack.ai.
    Dispatches rich webhook cards to Slack/Discord channels for high-value
    and deadline-expiring disputes. Never blocks or crashes primary workflows.
    """
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or SLACK_WEBHOOK_URL

    def notify_high_value_dispute(self, dispute: RazorpayDispute, win_probability: float, rule_fired: str) -> Dict[str, Any]:
        """
        Fires an alert when a dispute exceeds the ₹2,000 ceiling and requires human review.
        """
        message_card = {
            "text": f"🐗 *RazorBack.ai Alert: High-Value Dispute Escalated*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🐗 RazorBack.ai — High-Value Dispute Escalated",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Dispute ID:*\n`{dispute.id}`"},
                        {"type": "mrkdwn", "text": f"*Amount:*\n*₹{dispute.amount:,.2f}* (> ₹{AMOUNT_CEILING_INR:,.2f})"},
                        {"type": "mrkdwn", "text": f"*Win Probability:*\n*{win_probability * 100:.1f}%*"},
                        {"type": "mrkdwn", "text": f"*Reason Code:*\n`{dispute.reason_code}`"}
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"🔒 *Rule Triggered:* `{rule_fired}` | Held in 1-Click Human Review Queue"
                        }
                    ]
                }
            ]
        }

        # Log alert event in immutable ledger
        append_audit_event(
            dispute_id=dispute.id,
            event_type="alert_high_value_escalation_dispatched",
            payload_snapshot={
                "amount": dispute.amount,
                "ceiling": AMOUNT_CEILING_INR,
                "win_probability": win_probability,
                "slack_configured": bool(self.webhook_url)
            },
            actor="alert_bot"
        )

        return self._send_webhook(message_card)

    def notify_urgent_deadline(self, dispute: RazorpayDispute, hours_remaining: float) -> Dict[str, Any]:
        """
        Fires an urgent countdown alarm when a dispute hits < 12 hours before bank forfeiture.
        """
        message_card = {
            "text": f"🚨 *RazorBack.ai URGENT: SLA Deadline Expiring in {hours_remaining:.1f}h!*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🚨 URGENT SLA DEADLINE: {hours_remaining:.1f}h Remaining!",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Dispute ID:*\n`{dispute.id}`"},
                        {"type": "mrkdwn", "text": f"*Amount:*\n*₹{dispute.amount:,.2f}*"},
                        {"type": "mrkdwn", "text": f"*Deadline SLA:*\n*< {hours_remaining:.1f} Hours*"},
                        {"type": "mrkdwn", "text": f"*Status:*\n`{dispute.decision_status.value}`"}
                    ]
                }
            ]
        }

        append_audit_event(
            dispute_id=dispute.id,
            event_type="alert_urgent_sla_countdown_dispatched",
            payload_snapshot={
                "hours_remaining": hours_remaining,
                "amount": dispute.amount,
                "slack_configured": bool(self.webhook_url)
            },
            actor="alert_bot"
        )

        return self._send_webhook(message_card)

    def _send_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Safely dispatches webhook payload without crashing calling process."""
        if not self.webhook_url:
            return {"status": "skipped", "reason": "no_webhook_url_configured"}

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=3.0)
            return {"status": "dispatched", "status_code": resp.status_code}
        except Exception as e:
            logger.warning(f"Failed to post Slack alert webhook: {e}")
            return {"status": "failed", "error": str(e)}

# Global alert bot instance
alert_bot = AlertBot()
