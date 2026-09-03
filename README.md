# RazorBack.ai 🐗⚡
**Autonomous Chargeback Evidence Responder & Margin Defender**  
*Razorpay Hackathon — Track 02: AI Risk Manager*

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![XGBoost](https://img.shields.io/badge/ML-XGBoost-orange.svg)](https://xgboost.readthedocs.io/)
[![Tests Passing](https://img.shields.io/badge/Tests-30%2F30%20Passing-brightgreen.svg)]()
[![Design System](https://img.shields.io/badge/Font-Geist%20Mono-black.svg)]()

> **"Bites back at fraudulent chargebacks with verified proof & bounded autonomy."**

---

## 🎯 Executive Summary

In Indian D2C and online commerce, **chargebacks and payment disputes** are a silent margin killer. When a buyer disputes a charge with their issuing bank, merchants face tight `respond_by` SLA deadlines. The current operational reality is a chaotic scramble between Shopify orders, courier tracking dashboards (Shiprocket/Delhivery), and customer support logs. Most merchants default to either:
1. **Accepting all disputes:** Forfeiting 100% of revenue that was rightfully earned.
2. **Contesting blindly with generic text:** Losing anyway, wasting hours of ops time, and absorbing bank dispute penalty fees.

**RazorBack.ai** solves this end-to-end:
- **Instant Ingestion & Verification:** Listens to Razorpay `payment.dispute.created` webhooks with cryptographic HMAC SHA-256 verification.
- **Direct Logistics Integration:** Automatically pulls live AWB delivery timestamps, geo-coordinates, and digital recipient signatures directly from **Shiprocket & Delhivery** APIs.
- **Calibrated XGBoost Win Scorer:** Predicts win probability on a held-out test set with honest Precision, Recall, Confusion Matrix, and ₹ Cost of Errors (avoiding vibes-based rules).
- **Zero-Fabrication Evidence Assembly:** Maps order records, tax invoices, and courier PODs into Razorpay's official document category slots. It **never** fabricates evidence.
- **Bounded Decision Gate:** Enforces a hard **₹2,000 ceiling** before any deadline failsafe. High-value disputes *strictly* require 1-click human approval.
- **Real-Time Alert Bot:** Automatically alerts finance leads on Slack/Discord when high-value disputes breach ceilings or approach the 12-hour SLA deadline.
- **1-Click Cryptographic PDF Evidence Binder:** Generates watermarked, audit-grade evidence binders complete with SHA-256 event chain hashes for bank relationship managers.

---

## 🏗️ System Architecture

```
[Inbound Razorpay Webhook]
        │ (HMAC SHA-256 Verified)
        ▼
[SQLite Event Store (WAL Mode)]
        │
        ├──► [Feature Extractor] ──► [XGBoost Risk Scorer (Win Probability)]
        │
        ├──► [Carrier Client] ──► [Shiprocket / Delhivery Live AWB Telemetry]
        │
        └──► [Evidence Agent] ──► [Razorpay Documents API (/v1/documents)]
                                              │
                                              ▼
                                 [Bounded Decision Gate]
                                              │
               ┌──────────────────────────────┼──────────────────────────────┐
               ▼                              ▼                              ▼
     [Rule 1: > ₹2,000]             [Rule 2: < 12h SLA]          [Rule 4: P(win) >= 0.65]
       Held for Human Review         Auto-Submit Best Draft       Autonomous Contest
       + Slack Alert Bot             (Amount <= ₹2,000)           (Amount <= ₹2,000)
               │                              │                              │
               ▼                              ▼                              ▼
   [Ops Review Queue (1-Click)] ──► [PATCH /v1/disputes/:id/contest] ◄───────┘
                                              │
                                              ▼
                             [Immutable Audit Ledger Replay]
                               (SHA-256 Cryptographic Hash)
```

---

## 🔒 Bounded Autonomy & Decision Hierarchy

```
[Inbound Dispute]
       │
       ▼
[Rule 0: Upload Failure?] ── Yes ──► [ESCALATE (Never silent accept)]
       │ No
       ▼
[Rule 1: Amount > ₹2,000?] ── Yes ──► [CONTEST_DRAFT (Human Review Queue + Slack Alert)]
       │ No (<= ₹2,000)
       ▼
[Rule 2: Hours <= 12h & Comp >= 0.40?] ── Yes ──► [CONTEST_AUTO (Deadline Failsafe)]
       │ No
       ▼
[Rule 3: Amount <= ₹500 & WinProb <= 0.25?] ── Yes ──► [ACCEPT (Auto-concede Negative ROI)]
       │ No
       ▼
[Rule 4: WinProb >= 0.65 & Comp >= 0.70 & No Missing?] ── Yes ──► [CONTEST_AUTO]
       │ No
       ▼
[Rule 5: Default] ──► [CONTEST_DRAFT (Human Review Queue)]
```

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python 3.12+
- Modern Web Browser

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Aamod007/RazorBack.ai.git
cd RazorBack.ai
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```
*(Optionally populate your Razorpay Test Key, Secret, Webhook Secret, or Carrier API tokens. If left empty, RazorBack.ai runs in high-fidelity simulated sandbox mode).*

### 3. Launch Dashboard & API
```bash
python run.py
```
Visit the Ops Dashboard at: **`http://127.0.0.1:8000`**

---

## 🧪 Testing & Verification

Run the comprehensive pytest test suite covering end-to-end webhook ingestion, XGBoost scoring, carrier connectors, boundary failures, alert bots, and cryptographic binders:

```bash
pytest -v
```

**Results: 30 passed in 3.5s (100% Passing)**
- `tests/test_carrier_client.py`: Shiprocket/Delhivery AWB telemetry & digital recipient signatures.
- `tests/test_alert_bot.py`: Real-time Slack BlockKit notifications & non-blocking delivery.
- `tests/test_evidence_binder.py`: Printable HTML/PDF Evidence Binder rendering & SHA-256 verification.
- `tests/test_boundary_failures.py`: Duplicate webhook idempotency, decision gate guards, and ledger tampering checks.
- `tests/test_decision_gate.py`: Hard ₹2,000 ceiling, auto-contest thresholds, deadline failsafes.
- `tests/test_e2e_pipeline.py`: Complete HMAC webhook to Razorpay contest pipeline.
- `tests/test_evidence_agent.py`: Evidence slot assembly & zero-fabrication guard.
- `tests/test_failure_handling.py`: Exponential backoff and graceful escalation on upload failure.
- `tests/test_risk_scorer.py`: Stratified train/test evaluation with precision/recall curves.
- `tests/test_webhook.py`: HMAC signature validation and tampered payload rejection.

---

## 📡 API Surface Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/webhooks/razorpay` | Ingests `payment.dispute.*` webhooks with HMAC signature verification |
| `GET` | `/api/disputes` | Lists all disputes with status, win probabilities, and amounts |
| `GET` | `/api/disputes/{id}` | Fetches dispute detail, payment records, evidence slots, and decision logs |
| `POST` | `/api/disputes/{id}/approve` | Human analyst 1-click contest approval submitting to Razorpay API |
| `POST` | `/api/disputes/{id}/accept` | Concedes dispute via Razorpay API |
| `GET` | `/api/disputes/{id}/replay` | Returns chronological state machine replay with SHA-256 chain hash |
| `GET` | `/api/disputes/{id}/binder` | Generates 1-click printable/exportable Evidence Binder for bank managers |
| `GET` | `/api/evaluation/metrics` | Returns held-out 30% evaluation metrics, confusion matrix, and ₹ costs |
| `POST` | `/api/simulator/seed` | Triggers deterministic dispute archetypes for live hackathon evaluation |

---

## 📜 License
MIT License. Built for the Razorpay Hackathon Track 02 (AI Risk Manager).