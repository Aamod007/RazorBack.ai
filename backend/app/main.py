import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Depends, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import BASE_DIR, IS_LIVE_API_MODE, RAZORPAY_KEY_ID
from .database import (
    init_db, list_disputes, get_dispute, get_payment, get_evidence,
    get_decision, get_audit_events, update_dispute_status, append_audit_event,
    save_evidence, replay_dispute_events
)
from .models import (
    RazorpayDispute, DisputeDetailResponse, DecisionAction, DecisionStatus, DisputeStatus
)
from .webhook import router as webhook_router
from .risk_scorer import risk_scorer
from .evidence_agent import evidence_agent
from .decision_gate import decision_gate
from .razorpay_client import razorpay_client
from .feature_extractor import extract_features
from .evidence_binder import render_evidence_binder_html
from .simulator import (
    seed_simulated_dispute, run_autonomous_pipeline, DEMO_ARCHETYPES
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database & model
    init_db()
    risk_scorer._initialize_or_load_model()
    
    # Auto-seed initial queue if empty so evaluators see live data immediately
    existing = list_disputes(limit=5)
    if not existing:
        print("[RazorBack.ai] Seeding initial demo disputes...")
        seed_simulated_dispute("auto_contest_winnable")
        seed_simulated_dispute("over_ceiling_escalate")
        seed_simulated_dispute("no_fabrication_missing_proof")
        seed_simulated_dispute("auto_accept_low_roi")
    yield

app = FastAPI(
    title="RazorBack.ai API",
    description="Autonomous AI Risk Manager & Chargeback Evidence Responder for Razorpay Hackathon Track 02",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include webhook router
app.include_router(webhook_router)

# Models for request payloads
class ApproveContestRequest(BaseModel):
    analyst_id: str = "analyst_aamod"
    custom_summary: Optional[str] = None

class AcceptDisputeRequest(BaseModel):
    analyst_id: str = "analyst_aamod"
    reason: str = "Merchant agreed to customer chargeback"

class SeedDisputeRequest(BaseModel):
    archetype: str = "auto_contest_winnable"
    induce_failure: bool = False

# REST API Endpoints

@app.get("/api/system/status")
def get_system_status():
    """Returns current environment mode (Live Test API vs Sandbox Mode) and config."""
    return {
        "status": "online",
        "mode": "live_test_api" if IS_LIVE_API_MODE else "sandbox_demo_mode",
        "live_api_configured": IS_LIVE_API_MODE,
        "key_id_preview": f"{RAZORPAY_KEY_ID[:8]}..." if RAZORPAY_KEY_ID else "None (Using High-Fidelity Sandbox)",
        "server_time_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "available_archetypes": list(DEMO_ARCHETYPES.keys())
    }

@app.get("/api/disputes", response_model=List[RazorpayDispute])
def get_all_disputes(limit: int = 100):
    """Lists all tracked disputes in reverse chronological order."""
    return list_disputes(limit=limit)

@app.get("/api/disputes/{dispute_id}", response_model=DisputeDetailResponse)
def get_dispute_detail(dispute_id: str):
    """Fetches full dispute detail: entities, feature vector, ML win score, 10-slot evidence, and audit trail."""
    dispute = get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    payment = get_payment(dispute.payment_id)
    evidence = get_evidence(dispute_id)
    decision = get_decision(dispute_id)
    audit_events = get_audit_events(dispute_id)

    features = None
    if evidence:
        features = extract_features(dispute, payment, evidence)

    now = int(time.time())
    time_remaining_hours = max(0.0, (dispute.respond_by - now) / 3600.0) if dispute.respond_by > now else 0.0

    return DisputeDetailResponse(
        dispute=dispute,
        payment=payment,
        evidence=evidence,
        decision=decision,
        audit_events=audit_events,
        features=features,
        time_remaining_hours=round(time_remaining_hours, 1)
    )

@app.post("/api/disputes/{dispute_id}/approve")
def approve_contest(dispute_id: str, req: ApproveContestRequest = Body(...)):
    """Human analyst manually approves and submits drafted contest."""
    dispute = get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    evidence = get_evidence(dispute_id)
    if not evidence:
        raise HTTPException(status_code=400, detail="Evidence packet not assembled for dispute")

    summary = req.custom_summary or evidence.slots.get("explanation_letter", "")
    if len(summary) > 1000:
        raise HTTPException(status_code=400, detail="Explanation letter exceeds Razorpay 1000 char limit")

    # If custom summary provided, update packet
    if req.custom_summary:
        evidence.slots["explanation_letter"] = req.custom_summary
        save_evidence(evidence)

    # Format document references matching Razorpay schema
    doc_refs = evidence.uploaded_slot_docs if evidence.uploaded_slot_docs else {
        f"doc_{idx}": doc_id for idx, doc_id in enumerate(evidence.uploaded_doc_ids)
    }
    
    # Submit contest via Razorpay API
    res = razorpay_client.contest_dispute(
        dispute_id=dispute.id,
        summary=summary,
        documents=doc_refs,
        action="submit"
    )

    update_dispute_status(dispute_id, status=DisputeStatus.UNDER_REVIEW, decision_status=DecisionStatus.MANUALLY_CONTESTED)

    append_audit_event(
        dispute_id=dispute.id,
        event_type="human_contest_approved_and_submitted",
        payload_snapshot={
            "analyst_id": req.analyst_id,
            "razorpay_response": res,
            "custom_summary_used": bool(req.custom_summary)
        },
        actor=f"human:{req.analyst_id}"
    )

    return {"status": "success", "message": "Contest submitted to Razorpay", "result": res}

@app.post("/api/disputes/{dispute_id}/accept")
def accept_dispute_manually(dispute_id: str, req: AcceptDisputeRequest = Body(...)):
    """Human analyst manually concedes dispute."""
    dispute = get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    res = razorpay_client.accept_dispute(dispute_id)
    update_dispute_status(dispute_id, status=DisputeStatus.CLOSED, decision_status=DecisionStatus.MANUALLY_ACCEPTED)

    append_audit_event(
        dispute_id=dispute.id,
        event_type="human_dispute_accepted",
        payload_snapshot={
            "analyst_id": req.analyst_id,
            "reason": req.reason,
            "razorpay_response": res
        },
        actor=f"human:{req.analyst_id}"
    )

    return {"status": "success", "message": "Dispute accepted and closed", "result": res}

@app.post("/api/disputes/{dispute_id}/retry_upload")
def retry_document_upload(dispute_id: str):
    """Retries document uploads after a failure (§4.3) and re-evaluates decision."""
    dispute = get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    evidence = get_evidence(dispute_id)
    if not evidence:
        raise HTTPException(status_code=400, detail="Evidence packet not found")

    append_audit_event(
        dispute_id=dispute_id,
        event_type="manual_retry_upload_requested",
        payload_snapshot={"initiated_by": "analyst"},
        actor="human:analyst"
    )

    # Retry upload
    razorpay_client.set_induce_upload_failure(False)
    success, uploaded_doc_ids, err = evidence_agent.upload_packet_documents(evidence, max_attempts=3)
    save_evidence(evidence)

    payment = get_payment(dispute.payment_id)
    features = extract_features(dispute, payment, evidence)
    win_prob = risk_scorer.predict_win_probability(features)

    decision = decision_gate.evaluate(dispute, win_prob, evidence, upload_failed=not success)
    exec_result = decision_gate.execute_decision(dispute, decision, evidence)

    return {
        "status": "success" if success else "failed",
        "upload_status": evidence.upload_status,
        "decision": decision.action,
        "rule_fired": decision.rule_fired
    }

@app.get("/api/disputes/{dispute_id}/replay")
def get_dispute_replay(dispute_id: str):
    """
    Deterministically replays the immutable audit ledger for a dispute.
    Returns chronological timeline, state transitions, and cryptographic SHA-256 chain hash.
    """
    res = replay_dispute_events(dispute_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Dispute not found or no audit events recorded")
    return res

@app.get("/api/disputes/{dispute_id}/binder", response_class=HTMLResponse)
def get_evidence_binder(dispute_id: str):
    """
    Renders an executive, publication-grade printable HTML/PDF evidence binder
    for the dispute with verified cryptographic SHA-256 ledger proof.
    """
    dispute = get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    payment = get_payment(dispute.payment_id)
    evidence = get_evidence(dispute_id)
    decision = get_decision(dispute_id)
    replay_data = replay_dispute_events(dispute_id)

    html = render_evidence_binder_html(dispute, payment, evidence, decision, replay_data)
    return HTMLResponse(content=html)

@app.get("/api/evaluation/metrics")
def get_evaluation_metrics():
    """Returns held-out 30% evaluation report with honest precision/recall, confusion matrix, and ₹ costs."""
    return risk_scorer.eval_results

@app.post("/api/evaluation/retrain")
def retrain_evaluation():
    """Retrains the XGBoost model on a new synthetic split and returns fresh held-out evaluation."""
    metrics = risk_scorer.train_and_evaluate()
    return {"status": "success", "metrics": metrics}

@app.post("/api/simulator/seed")
def trigger_seed_dispute(req: SeedDisputeRequest = Body(...)):
    """Triggers dispute seeder to demonstrate specific hackathon scenarios (§4.4)."""
    res = seed_simulated_dispute(archetype_key=req.archetype, induce_failure=req.induce_failure)
    return {"status": "success", "seeded": res}

# Static Frontend mounting
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
