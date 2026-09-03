import hmac
import hashlib
import json
import logging
from typing import Tuple, Dict, Any, Optional
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks
from .config import WEBHOOK_SECRET
from .database import (
    save_dispute, save_payment, append_audit_event, get_dispute, update_dispute_status
)
from .models import (
    RazorpayDispute, RazorpayPayment, DisputeStatus, DecisionStatus, DisputeSource
)

logger = logging.getLogger("disputeguard.webhook")
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

def verify_razorpay_signature(body: bytes, signature: Optional[str], secret: str) -> bool:
    """Verifies X-Razorpay-Signature using HMAC-SHA256."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def compute_signature(body: bytes, secret: str) -> str:
    """Helper to compute valid HMAC signature for test/simulator payloads."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")
):
    raw_body = await request.body()
    
    # 1. Verify HMAC Signature
    if not verify_razorpay_signature(raw_body, x_razorpay_signature, WEBHOOK_SECRET):
        logger.warning("Rejected webhook: Invalid or missing X-Razorpay-Signature")
        # Still log security rejection to audit if dispute_id can be parsed
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            disp_id = parsed.get("payload", {}).get("dispute", {}).get("entity", {}).get("id", "unknown")
            append_audit_event(
                disp_id,
                "webhook_rejected_signature",
                {"reason": "Invalid HMAC signature", "signature_header": x_razorpay_signature},
                actor="security_guard"
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    event_type = data.get("event", "")
    payload = data.get("payload", {})
    dispute_entity = payload.get("dispute", {}).get("entity", {})
    payment_entity = payload.get("payment", {}).get("entity", {})

    if not dispute_entity:
        return {"status": "ignored", "reason": "No dispute entity in payload"}

    dispute_id = dispute_entity.get("id")
    if not dispute_id:
        return {"status": "ignored", "reason": "Missing dispute id"}

    # 2. Append raw event to Audit Log
    append_audit_event(
        dispute_id=dispute_id,
        event_type=f"webhook_{event_type}",
        payload_snapshot=data,
        actor="razorpay_webhook"
    )

    # 3. Parse and persist dispute & payment
    raw_amount = dispute_entity.get("amount", 0)
    # Razorpay amounts in webhook are usually in paise (100 paise = 1 INR)
    amount_inr = round(float(raw_amount) / 100.0, 2) if raw_amount > 1000 else float(raw_amount)
    
    dispute = RazorpayDispute(
        id=dispute_id,
        payment_id=dispute_entity.get("payment_id", payment_entity.get("id", "")),
        amount=amount_inr,
        currency=dispute_entity.get("currency", "INR"),
        amount_deducted=amount_inr,
        reason_code=dispute_entity.get("reason_code", "chargeback_unspecified"),
        phase=dispute_entity.get("phase", "chargeback"),
        respond_by=dispute_entity.get("respond_by", 0),
        status=DisputeStatus(dispute_entity.get("status", "open")),
        decision_status=DecisionStatus.PENDING_SCORING,
        source=DisputeSource(dispute_entity.get("source", "simulated")),
        created_at=dispute_entity.get("created_at", int(request.state.__dict__.get("now", 0) or 0))
    )
    save_dispute(dispute)

    if payment_entity:
        pay_amount = payment_entity.get("amount", 0)
        pay_amount_inr = round(float(pay_amount) / 100.0, 2) if pay_amount > 1000 else float(pay_amount)
        payment = RazorpayPayment(
            id=payment_entity.get("id"),
            order_id=payment_entity.get("order_id"),
            amount=pay_amount_inr,
            currency=payment_entity.get("currency", "INR"),
            method=payment_entity.get("method", "card"),
            email=payment_entity.get("email"),
            contact=payment_entity.get("contact"),
            created_at=payment_entity.get("created_at", 0)
        )
        save_payment(payment)

    # 4. Handle lifecycle events
    if event_type in ("payment.dispute.created", "payment.dispute.action_required"):
        # Import pipeline runner lazily to avoid circular dependencies
        from .simulator import run_autonomous_pipeline
        background_tasks.add_task(run_autonomous_pipeline, dispute_id)
    elif event_type in ("payment.dispute.won", "payment.dispute.lost", "payment.dispute.closed"):
        mapped_status = DisputeStatus.CLOSED
        if event_type == "payment.dispute.won":
            mapped_status = DisputeStatus.WON
        elif event_type == "payment.dispute.lost":
            mapped_status = DisputeStatus.LOST
        update_dispute_status(dispute_id, status=mapped_status, decision_status=DecisionStatus.CLOSED)

    return {
        "status": "success",
        "event": event_type,
        "dispute_id": dispute_id,
        "processed": True
    }
