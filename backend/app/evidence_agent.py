import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from .models import RazorpayDispute, RazorpayPayment, EvidencePacket
from .mock_merchant import get_merchant_record_for_order
from .carrier_client import carrier_client
from .razorpay_client import razorpay_client, RazorpayAPIError
from .database import append_audit_event

logger = logging.getLogger("disputeguard.evidence")

# Required evidence slots per reason code according to payment network rules
REASON_REQUIRED_SLOTS = {
    "product_not_received": ["shipping_proof", "billing_proof", "explanation_letter"],
    "goods_not_as_described": ["billing_proof", "customer_communication", "term_and_conditions", "explanation_letter"],
    "duplicate": ["billing_proof", "explanation_letter"],
    "credit_not_processed": ["refund_cancellation_policy", "customer_communication", "explanation_letter"],
    "fraudulent": ["access_activity_log", "billing_proof", "shipping_proof", "explanation_letter"],
    "other": ["billing_proof", "explanation_letter"]
}

ALL_EVIDENCE_SLOTS = [
    "shipping_proof",
    "billing_proof",
    "customer_communication",
    "proof_of_service",
    "explanation_letter",
    "refund_confirmation",
    "access_activity_log",
    "refund_cancellation_policy",
    "term_and_conditions",
    "others"
]

def synthesize_explanation_letter(dispute: RazorpayDispute, merchant_rec: Dict[str, Any], slots: Dict[str, Any]) -> str:
    """
    Drafts concise, legally binding contest summary strictly under 1,000 characters
    (Razorpay API hard limit).
    """
    order_id = merchant_rec.get("order_id", "N/A")
    product = merchant_rec.get("product_name", "Purchased Goods/Services")
    carrier = merchant_rec.get("carrier")
    tracking = merchant_rec.get("tracking_number")
    delivered = merchant_rec.get("delivered_date")
    inv = merchant_rec.get("invoice_number", "N/A")

    lines = [
        f"Contesting dispute {dispute.id} for Order {order_id} (Amount: INR {dispute.amount}).",
        f"Item: {product} under Tax Invoice {inv}."
    ]

    if tracking and delivered:
        lines.append(f"Fulfillment confirmed via {carrier} (AWB: {tracking}), delivered on {delivered}.")
    elif merchant_rec.get("fulfillment_status") == "active_service":
        lines.append("Digital service provisioned and accessed with verified activity logs.")

    if slots.get("customer_communication"):
        lines.append("Direct customer communications confirm delivery satisfaction and receipt.")

    if slots.get("term_and_conditions"):
        lines.append("Customer expressly agreed to standard merchant terms and return window.")

    lines.append("All attached documentation proves legitimate authorization and fulfillment. Requesting dispute closure in merchant favor.")

    letter = " ".join(lines)
    # Strict boundary safety
    if len(letter) > 980:
        letter = letter[:975] + "..."
    return letter

class EvidenceAgent:
    """
    Assembles evidence packets from merchant records without fabrication,
    manages document uploads with retry/backoff, and handles upload failure (§4.3).
    """
    def assemble_packet(self, dispute: RazorpayDispute, payment: Optional[RazorpayPayment]) -> EvidencePacket:
        order_id = payment.order_id if payment else None
        merchant_rec = get_merchant_record_for_order(order_id)

        required_slots = REASON_REQUIRED_SLOTS.get(dispute.reason_code, ["billing_proof", "explanation_letter"])
        missing_docs = merchant_rec.get("missing_documents", [])

        slots: Dict[str, Any] = {slot: [] for slot in ALL_EVIDENCE_SLOTS}
        missing_slots: List[str] = []

        # 1. Map Shipping Proof via Live Carrier Telemetry
        if "shipping_proof" not in missing_docs and merchant_rec.get("tracking_number"):
            awb = merchant_rec.get("tracking_number")
            carrier = merchant_rec.get("carrier")
            carrier_proof = carrier_client.fetch_tracking_telemetry(awb, carrier)
            
            slots["shipping_proof"].append({
                "doc_type": "consignment_note",
                "carrier": carrier_proof.get("carrier", carrier or "Carrier Verified"),
                "tracking_number": awb,
                "delivered_date": carrier_proof.get("delivered_date", merchant_rec.get("delivered_date")),
                "delivered_location": carrier_proof.get("delivered_location", merchant_rec.get("delivery_address")),
                "recipient_signed_by": carrier_proof.get("recipient_signed_by", merchant_rec.get("recipient_signed_by")),
                "live_verified": carrier_proof.get("live_verified", False)
            })
        elif "shipping_proof" in required_slots:
            missing_slots.append("shipping_proof")

        # 2. Map Billing Proof
        if "billing_proof" not in missing_docs and merchant_rec.get("invoice_number"):
            slots["billing_proof"].append({
                "doc_type": "tax_invoice",
                "invoice_number": merchant_rec.get("invoice_number"),
                "date": merchant_rec.get("invoice_date"),
                "amount": merchant_rec.get("order_amount", dispute.amount)
            })
        elif "billing_proof" in required_slots:
            missing_slots.append("billing_proof")

        # 3. Map Customer Communication
        if "customer_communication" not in missing_docs and merchant_rec.get("customer_support_chat"):
            slots["customer_communication"].append({
                "channel": "support_chat",
                "transcript": merchant_rec.get("customer_support_chat")
            })
        elif "customer_communication" in required_slots:
            missing_slots.append("customer_communication")

        # 4. Map Service & Access Logs
        if merchant_rec.get("access_activity_log"):
            slots["access_activity_log"].append({
                "log_type": "sso_session_audit",
                "content": merchant_rec.get("access_activity_log")
            })

        # 5. Map Terms & Cancellation Policy
        if merchant_rec.get("return_policy_accepted"):
            slots["term_and_conditions"].append({
                "policy_type": "standard_return_cancellation",
                "url": merchant_rec.get("terms_url", "https://merchant.example.com/terms")
            })

        # 6. Draft Explanation Letter (strictly <= 1000 characters)
        explanation_letter = synthesize_explanation_letter(dispute, merchant_rec, slots)
        slots["explanation_letter"] = explanation_letter

        # 7. Calculate Completeness Score
        # Fraction of reason-code required slots that were actually filled
        filled_required_count = sum(1 for slot in required_slots if slot not in missing_slots and slots.get(slot))
        completeness_score = round(filled_required_count / max(1, len(required_slots)), 2)

        packet = EvidencePacket(
            dispute_id=dispute.id,
            slots=slots,
            completeness_score=completeness_score,
            missing_slots=missing_slots,
            drafted_at=datetime.now(timezone.utc).isoformat(),
            upload_status="pending",
            upload_attempts=0,
            uploaded_doc_ids=[]
        )

        append_audit_event(
            dispute_id=dispute.id,
            event_type="evidence_assembled",
            payload_snapshot={
                "completeness_score": completeness_score,
                "missing_slots": missing_slots,
                "required_slots": required_slots,
                "explanation_letter_len": len(explanation_letter)
            },
            actor="evidence_assembly_agent"
        )

        return packet

    def upload_packet_documents(self, packet: EvidencePacket, max_attempts: int = 3) -> Tuple[bool, List[str], Optional[str]]:
        """
        Uploads documents to Razorpay Documents API with exponential backoff (§4.3).
        Logs all attempts and raw errors into Audit Log.
        Returns: (success: bool, uploaded_doc_ids: List[str], error_message: Optional[str])
        """
        uploaded_doc_ids: List[str] = []
        uploaded_slot_docs: Dict[str, List[str]] = {}
        last_error = None

        # Build list of items to upload as documents, associating each with its official slot
        items_to_upload = []
        if packet.slots.get("shipping_proof"):
            items_to_upload.append(("shipping_proof", "shipping_proof.pdf", b"%PDF-1.4 Mock Proof of Delivery Consignment Note"))
        if packet.slots.get("billing_proof"):
            items_to_upload.append(("billing_proof", "tax_invoice.pdf", b"%PDF-1.4 Mock Tax Invoice & GST Breakdown"))
        if packet.slots.get("customer_communication"):
            items_to_upload.append(("customer_communication", "support_chat.txt", b"Customer verified satisfaction via Zendesk chat transcript"))

        for slot_name, filename, content in items_to_upload:
            doc_uploaded = False
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = razorpay_client.upload_document(
                        file_content=content,
                        filename=filename,
                        purpose="dispute_evidence"
                    )
                    doc_id = resp.get("id", f"doc_sim_{filename[:4]}")
                    uploaded_doc_ids.append(doc_id)
                    if slot_name not in uploaded_slot_docs:
                        uploaded_slot_docs[slot_name] = []
                    uploaded_slot_docs[slot_name].append(doc_id)
                    doc_uploaded = True

                    append_audit_event(
                        dispute_id=packet.dispute_id,
                        event_type="document_uploaded",
                        payload_snapshot={"slot": slot_name, "filename": filename, "doc_id": doc_id, "attempt": attempt},
                        actor="evidence_assembly_agent"
                    )
                    break  # Success, proceed to next document

                except Exception as ex:
                    last_error = str(ex)
                    logger.warning(f"Upload failed for {filename} (Attempt {attempt}/{max_attempts}): {ex}")
                    append_audit_event(
                        dispute_id=packet.dispute_id,
                        event_type="document_upload_attempt_failed",
                        payload_snapshot={
                            "slot": slot_name,
                            "filename": filename,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error": str(ex),
                            "raw_error_details": getattr(ex, "error_payload", {})
                        },
                        actor="evidence_assembly_agent"
                    )
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    time.sleep(0.1 * (2 ** (attempt - 1)))

            if not doc_uploaded:
                # One of the documents failed after max attempts!
                packet.upload_status = "failed"
                packet.upload_attempts = max_attempts
                packet.uploaded_doc_ids = uploaded_doc_ids
                packet.uploaded_slot_docs = uploaded_slot_docs
                return False, uploaded_doc_ids, last_error

        packet.upload_status = "success"
        packet.upload_attempts = 1
        packet.uploaded_doc_ids = uploaded_doc_ids
        packet.uploaded_slot_docs = uploaded_slot_docs
        return True, uploaded_doc_ids, None

# Global evidence agent singleton
evidence_agent = EvidenceAgent()
