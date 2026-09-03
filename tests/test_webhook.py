import pytest
import json
import hmac
import hashlib
from backend.app.webhook import verify_razorpay_signature, compute_signature
from backend.app.config import WEBHOOK_SECRET

def test_signature_verification_valid():
    payload = json.dumps({"event": "payment.dispute.created", "test": 123}).encode("utf-8")
    sig = compute_signature(payload, WEBHOOK_SECRET)
    assert verify_razorpay_signature(payload, sig, WEBHOOK_SECRET) is True

def test_signature_verification_invalid():
    payload = json.dumps({"event": "payment.dispute.created"}).encode("utf-8")
    fake_sig = "a" * 64
    assert verify_razorpay_signature(payload, fake_sig, WEBHOOK_SECRET) is False

def test_signature_verification_tampered_payload():
    payload1 = json.dumps({"amount": 1000}).encode("utf-8")
    payload2 = json.dumps({"amount": 9000}).encode("utf-8")
    sig1 = compute_signature(payload1, WEBHOOK_SECRET)
    assert verify_razorpay_signature(payload2, sig1, WEBHOOK_SECRET) is False

def test_missing_signature_or_secret():
    payload = b"{}"
    assert verify_razorpay_signature(payload, None, WEBHOOK_SECRET) is False
    assert verify_razorpay_signature(payload, "abc", "") is False
