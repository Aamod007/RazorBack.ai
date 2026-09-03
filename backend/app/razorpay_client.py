import time
import uuid
import logging
from typing import Dict, Any, Optional
import requests
from .config import (
    IS_LIVE_API_MODE, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_BASE_URL
)

logger = logging.getLogger("disputeguard.razorpay")

class RazorpayAPIError(Exception):
    def __init__(self, status_code: int, message: str, error_payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_payload = error_payload or {}

class RazorpayClient:
    """
    Dual-mode Razorpay Disputes API client.
    Runs against live Razorpay Test Mode API when keys are provided,
    or falls back to high-fidelity sandbox mode with induced-failure capabilities.
    """
    def __init__(self):
        self.is_live = IS_LIVE_API_MODE
        self.key_id = RAZORPAY_KEY_ID
        self.key_secret = RAZORPAY_KEY_SECRET
        self.base_url = RAZORPAY_BASE_URL
        
        # In-memory document & contest mock store for sandbox mode
        self._mock_documents: Dict[str, Dict[str, Any]] = {}
        self._mock_contests: Dict[str, Dict[str, Any]] = {}
        self._mock_accepts: Dict[str, Dict[str, Any]] = {}
        
        # Induced failure flag for Hackathon Demo §4.3
        self.induce_upload_failure: bool = False
        self.upload_failure_count: int = 0

    def set_induce_upload_failure(self, state: bool):
        """Toggle induced 500 error on document uploads to demo graceful failure handling."""
        self.induce_upload_failure = state
        self.upload_failure_count = 0

    def get_dispute(self, dispute_id: str, expand_payment: bool = True) -> Dict[str, Any]:
        """GET /v1/disputes/:id?expand[]=payment"""
        if self.is_live:
            url = f"{self.base_url}/disputes/{dispute_id}"
            params = {"expand[]": "payment"} if expand_payment else {}
            resp = requests.get(url, auth=(self.key_id, self.key_secret), params=params, timeout=10)
            if resp.status_code != 200:
                raise RazorpayAPIError(resp.status_code, f"Failed to fetch dispute: {resp.text}", resp.json() if resp.headers.get("content-type") == "application/json" else {})
            return resp.json()
        else:
            # High-fidelity mock response matching official Razorpay Dispute entity
            return {
                "id": dispute_id,
                "entity": "dispute",
                "payment_id": f"pay_{dispute_id[-10:]}",
                "amount": 349900,  # paise
                "currency": "INR",
                "amount_deducted": 349900,
                "reason_code": "goods_not_as_described",
                "phase": "chargeback",
                "status": "open",
                "respond_by": int(time.time() + 86400 * 3),  # 3 days remaining
                "created_at": int(time.time() - 3600 * 4),
                "source": "simulated"
            }

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """GET /v1/payments/:id"""
        if self.is_live:
            url = f"{self.base_url}/payments/{payment_id}"
            resp = requests.get(url, auth=(self.key_id, self.key_secret), timeout=10)
            if resp.status_code != 200:
                raise RazorpayAPIError(resp.status_code, f"Failed to fetch payment: {resp.text}")
            return resp.json()
        else:
            return {
                "id": payment_id,
                "entity": "payment",
                "amount": 349900,
                "currency": "INR",
                "status": "captured",
                "order_id": "order_winnable_physical_01",
                "method": "card",
                "email": "customer@example.com",
                "contact": "+919876543210",
                "created_at": int(time.time() - 86400 * 5)
            }

    def upload_document(self, file_content: bytes, filename: str, purpose: str = "dispute_evidence") -> Dict[str, Any]:
        """
        POST /v1/documents with purpose=dispute_evidence
        Returns dict with id (e.g. doc_...).
        Supports induced failure (§4.3) with simulated 500 error.
        """
        if self.induce_upload_failure:
            self.upload_failure_count += 1
            logger.warning(f"Induced upload failure triggered (attempt {self.upload_failure_count})")
            raise RazorpayAPIError(
                503,
                "Razorpay Document Gateway Timeout (Induced Failure Demo §4.3)",
                {"error": {"code": "GATEWAY_TIMEOUT", "description": "Document storage subsystem temporarily unavailable."}}
            )

        if self.is_live:
            url = f"{self.base_url}/documents"
            files = {"file": (filename, file_content, "application/octet-stream")}
            data = {"purpose": purpose}
            resp = requests.post(url, auth=(self.key_id, self.key_secret), files=files, data=data, timeout=15)
            if resp.status_code not in (200, 201):
                raise RazorpayAPIError(resp.status_code, f"Failed to upload document: {resp.text}")
            return resp.json()
        else:
            doc_id = f"doc_{uuid.uuid4().hex[:14]}"
            doc_record = {
                "id": doc_id,
                "entity": "document",
                "purpose": purpose,
                "name": filename,
                "size": len(file_content),
                "created_at": int(time.time())
            }
            self._mock_documents[doc_id] = doc_record
            return doc_record

    def contest_dispute(self, dispute_id: str, summary: str, documents: Dict[str, Any], action: str = "submit") -> Dict[str, Any]:
        """
        PATCH /v1/disputes/:id/contest
        summary is strictly <= 1000 characters.
        action="submit" permanently submits the contest; omitting or draft keeps it saved.
        """
        if len(summary) > 1000:
            raise ValueError(f"Summary exceeds Razorpay limit of 1000 characters (length: {len(summary)})")

        payload = {
            "summary": summary,
            "documents": documents
        }
        if action == "submit":
            payload["action"] = "submit"

        if self.is_live:
            url = f"{self.base_url}/disputes/{dispute_id}/contest"
            resp = requests.patch(url, auth=(self.key_id, self.key_secret), json=payload, timeout=10)
            if resp.status_code not in (200, 201):
                raise RazorpayAPIError(resp.status_code, f"Failed to contest dispute: {resp.text}")
            return resp.json()
        else:
            res = {
                "id": dispute_id,
                "entity": "dispute",
                "status": "under_review" if action == "submit" else "open",
                "contest_state": "submitted" if action == "submit" else "draft",
                "summary": summary,
                "documents": documents,
                "updated_at": int(time.time())
            }
            self._mock_contests[dispute_id] = res
            return res

    def accept_dispute(self, dispute_id: str) -> Dict[str, Any]:
        """
        POST /v1/disputes/:id/accept
        Irreversible merchant action to concede dispute.
        """
        if self.is_live:
            url = f"{self.base_url}/disputes/{dispute_id}/accept"
            resp = requests.post(url, auth=(self.key_id, self.key_secret), json={}, timeout=10)
            if resp.status_code not in (200, 201):
                raise RazorpayAPIError(resp.status_code, f"Failed to accept dispute: {resp.text}")
            return resp.json()
        else:
            res = {
                "id": dispute_id,
                "entity": "dispute",
                "status": "closed",
                "closed_at": int(time.time()),
                "reason": "accepted_by_merchant"
            }
            self._mock_accepts[dispute_id] = res
            return res

# Global client singleton
razorpay_client = RazorpayClient()
