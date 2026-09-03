from typing import Dict, Any, Optional

# Realistic merchant database containing fulfillment, invoices, support transcripts, and activity logs
MOCK_MERCHANT_RECORDS: Dict[str, Dict[str, Any]] = {
    # Strong winnable physical goods case: complete tracking + invoice + delivery confirmation
    "order_winnable_physical_01": {
        "order_id": "order_winnable_physical_01",
        "product_name": "UltraSound Pro ANC Wireless Headphones",
        "order_amount": 3499.0,
        "fulfillment_status": "delivered",
        "carrier": "Blue Dart Express",
        "tracking_number": "BLUEDART-849204192",
        "dispatch_date": "2026-08-20T10:30:00Z",
        "delivered_date": "2026-08-23T14:15:00Z",
        "delivery_address": "Flat 402, Green Glen Heights, Bellandur, Bangalore 560103",
        "recipient_signed_by": "Rohan Sharma (Self)",
        "invoice_number": "INV-2026-8941",
        "invoice_date": "2026-08-20",
        "customer_support_chat": (
            "Customer (2026-08-24 11:02): 'Hi, I received my headphones, sound quality is great!'\n"
            "Support: 'Glad to hear! Let us know if you need anything else.'"
        ),
        "return_policy_accepted": True,
        "terms_url": "https://merchant.example.com/terms",
        "missing_documents": []
    },

    # Strong winnable SaaS / Digital Service case: verified login logs + active subscription + terms
    "order_winnable_saas_02": {
        "order_id": "order_winnable_saas_02",
        "product_name": "DevCloud Team Subscription (Annual)",
        "order_amount": 4200.0,
        "fulfillment_status": "active_service",
        "service_activation_date": "2026-08-15T09:00:00Z",
        "user_email": "dev.lead@techcorp.in",
        "access_activity_log": (
            "2026-08-15 09:02:11 IP 103.21.14.88 - User logged in via SSO\n"
            "2026-08-18 14:22:45 IP 103.21.14.88 - Provisioned 4 cloud environments\n"
            "2026-08-28 17:40:02 IP 103.21.14.88 - API key generated, 12,400 requests served"
        ),
        "invoice_number": "INV-SAAS-5502",
        "invoice_date": "2026-08-15",
        "return_policy_accepted": True,
        "terms_url": "https://devcloud.example.com/legal/terms",
        "missing_documents": []
    },

    # Missing shipping proof case (tests NO-FABRICATION RULE & ESCALATION):
    # Order was placed, but courier tracking was lost or pending
    "order_missing_shipping_03": {
        "order_id": "order_missing_shipping_03",
        "product_name": "Smart Fitness Band v4",
        "order_amount": 2899.0,
        "fulfillment_status": "in_transit_unverified",
        "carrier": "Local Courier",
        "tracking_number": None,  # Intentionally missing!
        "dispatch_date": "2026-08-25T16:00:00Z",
        "delivered_date": None,
        "invoice_number": "INV-2026-9012",
        "invoice_date": "2026-08-25",
        "customer_support_chat": (
            "Customer: 'Where is my parcel? The tracking link doesn't work.'\n"
            "Support: 'Checking with courier hub...'"
        ),
        "return_policy_accepted": True,
        "missing_documents": ["shipping_proof"]  # Missing slot!
    },

    # Unwinnable / High loss case: duplicate charge admitted or refund promised but stuck
    "order_unwinnable_dup_04": {
        "order_id": "order_unwinnable_dup_04",
        "product_name": "Coffee Roasters Sampler Pack",
        "order_amount": 450.0,
        "fulfillment_status": "duplicate_billing_error",
        "invoice_number": "INV-2026-8821",
        "customer_support_chat": (
            "Customer: 'I was charged twice on my card for the same coffee bag.'\n"
            "Support: 'We see the double swipe error on payment gateway. We will refund.'"
        ),
        "refund_notes": "Internal gateway sync failed, customer charged twice.",
        "missing_documents": ["shipping_proof", "proof_of_service"]
    },

    # High value dispute case (above ₹5,000 ceiling -> must escalate to Human Queue)
    "order_high_value_05": {
        "order_id": "order_high_value_05",
        "product_name": "Enterprise Server Rack Accessory Kit",
        "order_amount": 18500.0,  # > ₹5,000 ceiling!
        "fulfillment_status": "delivered",
        "carrier": "FedEx Priority",
        "tracking_number": "FDX-993810291",
        "delivered_date": "2026-08-10T12:00:00Z",
        "recipient_signed_by": "Warehouse Mgr (PO-442)",
        "invoice_number": "INV-ENT-2026-019",
        "customer_support_chat": "Procurement query regarding warranty extension.",
        "return_policy_accepted": True,
        "missing_documents": []
    }
}

def get_merchant_record_for_order(order_id: Optional[str]) -> Dict[str, Any]:
    """Look up merchant order records or return dynamic fallback based on pattern."""
    if not order_id:
        return MOCK_MERCHANT_RECORDS["order_winnable_physical_01"]
    
    if order_id in MOCK_MERCHANT_RECORDS:
        return MOCK_MERCHANT_RECORDS[order_id]

    # Generate consistent record for seeded orders
    if "saas" in order_id.lower() or "service" in order_id.lower():
        return {
            "order_id": order_id,
            "product_name": "Cloud API Microservice Plan",
            "order_amount": 2500.0,
            "fulfillment_status": "active_service",
            "access_activity_log": "Active sessions logged from authenticated user domain.",
            "invoice_number": f"INV-{order_id[-6:]}",
            "return_policy_accepted": True,
            "missing_documents": []
        }
    elif "missing" in order_id.lower() or "nofab" in order_id.lower():
        return {
            "order_id": order_id,
            "product_name": "Vintage Leather Jacket",
            "order_amount": 4200.0,
            "fulfillment_status": "pending_carrier_receipt",
            "tracking_number": None,
            "invoice_number": f"INV-{order_id[-6:]}",
            "missing_documents": ["shipping_proof"]
        }
    else:
        return {
            "order_id": order_id,
            "product_name": "Wireless Ergonomic Mouse",
            "order_amount": 1899.0,
            "fulfillment_status": "delivered",
            "carrier": "Blue Dart Express",
            "tracking_number": f"BD-{order_id[-8:]}",
            "delivered_date": "2026-08-22T15:00:00Z",
            "recipient_signed_by": "Customer Signature Confirmed",
            "invoice_number": f"INV-{order_id[-6:]}",
            "return_policy_accepted": True,
            "missing_documents": []
        }
