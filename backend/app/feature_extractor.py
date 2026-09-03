import time
from typing import Dict, Any, Tuple
import numpy as np
from .models import RazorpayDispute, RazorpayPayment, EvidencePacket
from .mock_merchant import get_merchant_record_for_order

REASON_CODES = [
    "fraudulent",
    "product_not_received",
    "credit_not_processed",
    "duplicate",
    "goods_not_as_described",
    "other"
]

PHASES = ["fraud", "pre_arbitration", "chargeback", "arbitration"]
PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]

# Historical win rates across reasons based on standard chargeback benchmarks
HISTORICAL_WIN_RATES = {
    "product_not_received": 0.74,
    "goods_not_as_described": 0.62,
    "duplicate": 0.88,
    "credit_not_processed": 0.45,
    "fraudulent": 0.32,
    "other": 0.50
}

def extract_features(
    dispute: RazorpayDispute,
    payment: RazorpayPayment,
    evidence: EvidencePacket,
    customer_prior_disputes: int = 0
) -> Dict[str, Any]:
    """
    Extracts structured, human-interpretable feature dictionary for a dispute.
    """
    now = int(time.time())
    response_window_hours = max(1.0, (dispute.respond_by - dispute.created_at) / 3600.0) if dispute.respond_by > dispute.created_at else 72.0
    time_remaining_hours = max(0.0, (dispute.respond_by - now) / 3600.0) if dispute.respond_by > now else 0.0

    merchant_rec = get_merchant_record_for_order(payment.order_id) if payment else {}
    fulfillment_status = merchant_rec.get("fulfillment_status", "unknown")
    order_fulfillment_confirmed = 1 if fulfillment_status in ("delivered", "active_service") else 0

    reason = dispute.reason_code if dispute.reason_code in REASON_CODES else "other"
    historical_win_rate = HISTORICAL_WIN_RATES.get(reason, 0.50)

    method = payment.method if payment and payment.method in PAYMENT_METHODS else "card"
    phase = dispute.phase if dispute.phase in PHASES else "chargeback"

    return {
        "dispute_id": dispute.id,
        "reason_code": reason,
        "phase": phase,
        "amount_inr": dispute.amount,
        "response_window_hours": round(response_window_hours, 2),
        "time_remaining_hours": round(time_remaining_hours, 2),
        "payment_method": method,
        "merchant_historical_win_rate": historical_win_rate,
        "order_fulfillment_confirmed": order_fulfillment_confirmed,
        "evidence_completeness_score": round(evidence.completeness_score, 2),
        "customer_prior_disputes": customer_prior_disputes
    }

def vector_from_features(features: Dict[str, Any]) -> np.ndarray:
    """
    Converts feature dictionary into a 1D numerical vector for XGBoost.
    Encoding:
    - Reason code: one-hot (6)
    - Phase: one-hot (4)
    - Amount (log-scaled) (1)
    - Response window hours (norm) (1)
    - Time remaining hours (norm) (1)
    - Payment method: one-hot (4)
    - Historical win rate (1)
    - Order fulfillment confirmed (1)
    - Evidence completeness score (1)
    - Customer prior disputes (1)
    Total dimensions: 6 + 4 + 1 + 1 + 1 + 4 + 1 + 1 + 1 + 1 = 21 features
    """
    vec = []

    # One-hot reason code
    reason = features.get("reason_code", "other")
    for r in REASON_CODES:
        vec.append(1.0 if reason == r else 0.0)

    # One-hot phase
    phase = features.get("phase", "chargeback")
    for p in PHASES:
        vec.append(1.0 if phase == p else 0.0)

    # Numerical features
    amount = float(features.get("amount_inr", 1000.0))
    vec.append(np.log1p(max(0.0, amount)))

    resp_win = float(features.get("response_window_hours", 72.0))
    vec.append(resp_win / 168.0)  # Normalized to week

    time_rem = float(features.get("time_remaining_hours", 48.0))
    vec.append(time_rem / 168.0)

    # One-hot payment method
    method = features.get("payment_method", "card")
    for m in PAYMENT_METHODS:
        vec.append(1.0 if method == m else 0.0)

    # Contextual features
    vec.append(float(features.get("merchant_historical_win_rate", 0.50)))
    vec.append(float(features.get("order_fulfillment_confirmed", 0.0)))
    vec.append(float(features.get("evidence_completeness_score", 0.0)))
    vec.append(float(features.get("customer_prior_disputes", 0.0)))

    return np.array(vec, dtype=np.float32)
