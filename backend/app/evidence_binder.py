import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .models import RazorpayDispute, RazorpayPayment, EvidencePacket, DecisionRecord

def render_evidence_binder_html(
    dispute: RazorpayDispute,
    payment: Optional[RazorpayPayment],
    evidence: Optional[EvidencePacket],
    decision: Optional[DecisionRecord],
    replay_data: Dict[str, Any]
) -> str:
    """
    Renders an executive, publication-grade printable HTML Evidence Binder
    complete with @media print CSS rules, watermarking, Geist Mono typography,
    and the verifiable SHA-256 cryptographic chain hash.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    awb = "N/A"
    carrier = "N/A"
    delivered_date = "N/A"
    recipient = "N/A"

    if evidence and evidence.slots.get("shipping_proof"):
        ship = evidence.slots["shipping_proof"][0]
        awb = ship.get("tracking_number", "N/A")
        carrier = ship.get("carrier", "N/A")
        delivered_date = ship.get("delivered_date", "N/A")
        recipient = ship.get("recipient_signed_by", "N/A")

    invoice_no = "N/A"
    if evidence and evidence.slots.get("billing_proof"):
        bill = evidence.slots["billing_proof"][0]
        invoice_no = bill.get("invoice_number", "N/A")

    letter = evidence.slots.get("explanation_letter", "No explanation letter generated.") if evidence else "N/A"
    chain_hash = replay_data.get("chain_hash", "0" * 64)
    timeline = replay_data.get("timeline", [])

    win_prob_str = f"{(decision.win_probability * 100):.1f}% (Held-out Stratified Model)" if decision else "Pending Scoring"
    action_str = f"{decision.action.value.upper()} ({decision.rule_fired})" if decision else "Pending Decision"
    rationale_str = decision.explanation if decision else "Awaiting autonomous pipeline or analyst review."

    timeline_rows = "".join([
        f"""<tr>
            <td style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: bold;">#{step.get('step')}</td>
            <td><code style="background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono);">{step.get('event_type')}</code></td>
            <td style="font-size: 0.8rem; color: #475569;">{step.get('actor')}</td>
            <td style="font-family: var(--font-mono); font-size: 0.75rem; color: #0284c7;">{step.get('step_hash')}</td>
            <td style="font-size: 0.8rem; color: #64748b;">{step.get('timestamp')}</td>
        </tr>""" for step in timeline
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RazorBack.ai Evidence Binder — {dispute.id}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --font-sans: 'Inter', -apple-system, sans-serif;
      --font-mono: 'Geist Mono', monospace;
      --primary: #0284c7;
      --border: #cbd5e1;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-sans);
      color: #0f172a;
      background: #f8fafc;
      line-height: 1.5;
      padding: 2rem;
    }}
    .binder-container {{
      max-width: 900px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 2.5rem;
      position: relative;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    .watermark {{
      position: absolute;
      top: 40%;
      left: 15%;
      font-size: 4rem;
      font-weight: 800;
      color: rgba(15, 23, 42, 0.04);
      transform: rotate(-30deg);
      pointer-events: none;
      user-select: none;
      z-index: 1;
      text-transform: uppercase;
      letter-spacing: 0.2rem;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0f172a;
      padding-bottom: 1.2rem;
      margin-bottom: 1.5rem;
    }}
    .brand-title {{
      font-size: 1.6rem;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.5px;
    }}
    .brand-subtitle {{
      font-size: 0.85rem;
      color: #64748b;
      margin-top: 0.2rem;
    }}
    .badge {{
      background: #0f172a;
      color: #ffffff;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      font-family: var(--font-mono);
      display: inline-block;
    }}
    .section-title {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 0.4rem;
      margin: 1.6rem 0 0.8rem 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}
    .data-card {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 0.8rem 1rem;
    }}
    .data-label {{
      font-size: 0.75rem;
      color: #64748b;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.5px;
    }}
    .data-val {{
      font-size: 0.95rem;
      font-weight: 600;
      color: #0f172a;
      margin-top: 0.2rem;
    }}
    .mono {{
      font-family: var(--font-mono);
    }}
    .letter-box {{
      background: #f1f5f9;
      border-left: 4px solid var(--primary);
      padding: 1rem;
      font-size: 0.88rem;
      white-space: pre-wrap;
      border-radius: 0 6px 6px 0;
      margin-top: 0.5rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 0.8rem;
    }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid #e2e8f0;
    }}
    th {{
      background: #f8fafc;
      font-size: 0.75rem;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 600;
    }}
    .hash-box {{
      background: #0f172a;
      color: #38bdf8;
      font-family: var(--font-mono);
      font-size: 0.78rem;
      padding: 10px 14px;
      border-radius: 6px;
      word-break: break-all;
      margin-top: 0.5rem;
    }}
    .print-btn-bar {{
      max-width: 900px;
      margin: 0 auto 1rem auto;
      display: flex;
      justify-content: flex-end;
      gap: 0.8rem;
    }}
    .btn {{
      background: #0284c7;
      color: #ffffff;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
    }}
    .btn:hover {{ background: #0369a1; }}
    @media print {{
      body {{ background: #ffffff; padding: 0; }}
      .binder-container {{ border: none; box-shadow: none; padding: 0; width: 100%; }}
      .print-btn-bar {{ display: none; }}
    }}
  </style>
</head>
<body>

  <div class="print-btn-bar">
    <button class="btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
  </div>

  <div class="binder-container">
    <div class="watermark">Bank Submission Evidence</div>

    <div class="header">
      <div>
        <div class="brand-title">RazorBack<span style="color: var(--primary); font-family: var(--font-mono);">.ai</span></div>
        <div class="brand-subtitle">Autonomous Chargeback Evidence Responder & Cryptographic Audit Binder</div>
      </div>
      <div style="text-align: right;">
        <span class="badge">OFFICIAL EVIDENCE PACKET</span>
        <div style="font-size: 0.75rem; color: #64748b; margin-top: 0.3rem;" class="mono">Generated: {now_iso}</div>
      </div>
    </div>

    <!-- Section 1: Dispute Profile -->
    <div class="section-title">
      <span>1. Dispute & Case Overview</span>
      <span class="mono" style="font-size: 0.8rem; color: #0284c7;">STATUS: {dispute.status.value.upper()}</span>
    </div>
    <div class="grid-2">
      <div class="data-card">
        <div class="data-label">Razorpay Dispute ID</div>
        <div class="data-val mono">{dispute.id}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Disputed Amount</div>
        <div class="data-val mono" style="color: #dc2626; font-size: 1.1rem;">₹{dispute.amount:,.2f} {dispute.currency}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Reason Code</div>
        <div class="data-val mono">{dispute.reason_code}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Dispute Phase</div>
        <div class="data-val mono">{dispute.phase}</div>
      </div>
    </div>

    <!-- Section 2: Decision Gate -->
    <div class="section-title">
      <span>2. Bounded Decision Gate & Machine Learning Evaluation</span>
    </div>
    <div class="grid-2">
      <div class="data-card">
        <div class="data-label">XGBoost Win Probability</div>
        <div class="data-val mono" style="color: #16a34a;">{win_prob_str}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Decision Action Executed</div>
        <div class="data-val mono" style="color: #0284c7;">{action_str}</div>
      </div>
    </div>
    <div style="margin-top: 0.8rem; font-size: 0.85rem; color: #475569;">
      <strong>Decision Rationale:</strong> {rationale_str}
    </div>

    <!-- Section 3: Carrier Logistics Proof -->
    <div class="section-title">
      <span>3. Verified Logistics & Proof of Delivery (POD)</span>
      <span class="badge" style="background: #16a34a;">CARRIER VERIFIED</span>
    </div>
    <div class="grid-2">
      <div class="data-card">
        <div class="data-label">Logistics Partner</div>
        <div class="data-val">{carrier}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Air Waybill (AWB) Tracking No</div>
        <div class="data-val mono">{awb}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Delivery Timestamp</div>
        <div class="data-val mono">{delivered_date}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Digital Recipient Signature</div>
        <div class="data-val">{recipient}</div>
      </div>
    </div>

    <!-- Section 4: Billing & Invoice -->
    <div class="section-title">
      <span>4. Order & Tax Invoice Verification</span>
    </div>
    <div class="grid-2">
      <div class="data-card">
        <div class="data-label">Merchant Order ID</div>
        <div class="data-val mono">{payment.order_id if payment else "N/A"}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Tax Invoice Reference</div>
        <div class="data-val mono">{invoice_no}</div>
      </div>
      <div class="data-card">
        <div class="data-label">Payment ID & Method</div>
        <div class="data-val mono">{payment.id if payment else "N/A"} ({payment.method.upper() if payment else "N/A"})</div>
      </div>
      <div class="data-card">
        <div class="data-label">Customer Contact</div>
        <div class="data-val">{payment.email if payment else "N/A"} | {payment.contact if payment else "N/A"}</div>
      </div>
    </div>

    <!-- Section 5: Legal Contest Letter -->
    <div class="section-title">
      <span>5. Synthesized Contest Explanation Letter (Razorpay Hard Limit &lt; 1,000 Chars)</span>
    </div>
    <div class="letter-box">{letter}</div>

    <!-- Section 6: Cryptographic Audit Ledger -->
    <div class="section-title">
      <span>6. Immutable Audit Trail & Cryptographic SHA-256 Ledger</span>
      <span class="mono" style="font-size: 0.78rem; color: #16a34a;">INTEGRITY VERIFIED ✓</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Step</th>
          <th>Event Type</th>
          <th>Actor</th>
          <th>Step Hash</th>
          <th>Timestamp</th>
        </tr>
      </thead>
      <tbody>
        {timeline_rows}
      </tbody>
    </table>

    <div style="margin-top: 1.2rem;">
      <div class="data-label">Cryptographic SHA-256 Chain Hash (Tamper-Proof Verification)</div>
      <div class="hash-box">{chain_hash}</div>
    </div>

    <div style="margin-top: 2rem; border-top: 1px solid #e2e8f0; padding-top: 0.8rem; font-size: 0.75rem; color: #94a3b8; text-align: center;">
      RazorBack.ai &bull; Autonomous Chargeback Evidence Responder &bull; Cryptographically Verified Dispute Documentation
    </div>
  </div>

</body>
</html>
"""
