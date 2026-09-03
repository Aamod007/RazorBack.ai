from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class DisputeStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    ACTION_REQUIRED = "action_required"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"

class DecisionAction(str, Enum):
    ACCEPT = "accept"
    CONTEST_DRAFT = "contest_draft"
    CONTEST_AUTO = "contest_auto"
    ESCALATE = "escalate"

class DecisionStatus(str, Enum):
    PENDING_SCORING = "pending_scoring"
    AUTO_CONTESTED = "auto_contested"
    DRAFT_PENDING_REVIEW = "draft_pending_review"
    AUTO_ACCEPTED = "auto_accepted"
    MANUALLY_CONTESTED = "manually_contested"
    MANUALLY_ACCEPTED = "manually_accepted"
    UPLOAD_FAILED_REVIEW = "upload_failed_review"
    CLOSED = "closed"

class DisputeSource(str, Enum):
    LIVE = "live"
    SIMULATED = "simulated"

class RazorpayDispute(BaseModel):
    id: str
    payment_id: str
    amount: float  # In INR
    currency: str = "INR"
    amount_deducted: float
    reason_code: str
    phase: str
    respond_by: int  # Unix timestamp
    status: DisputeStatus = DisputeStatus.OPEN
    decision_status: DecisionStatus = DecisionStatus.PENDING_SCORING
    source: DisputeSource = DisputeSource.SIMULATED
    created_at: int
    updated_at: Optional[int] = None

class RazorpayPayment(BaseModel):
    id: str
    order_id: Optional[str] = None
    amount: float  # In INR
    currency: str = "INR"
    method: str
    email: Optional[str] = None
    contact: Optional[str] = None
    created_at: int

class EvidencePacket(BaseModel):
    dispute_id: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    completeness_score: float = 0.0
    missing_slots: List[str] = Field(default_factory=list)
    drafted_at: Optional[str] = None
    submitted_at: Optional[str] = None
    upload_status: str = "pending"  # pending, success, partial, failed
    upload_attempts: int = 0
    uploaded_doc_ids: List[str] = Field(default_factory=list)
    uploaded_slot_docs: Dict[str, List[str]] = Field(default_factory=dict)

class DecisionRecord(BaseModel):
    dispute_id: str
    win_probability: float
    action: DecisionAction
    rule_fired: str
    actor: str  # agent or human:<id>
    timestamp: str
    explanation: str

class AuditEventRecord(BaseModel):
    id: Optional[int] = None
    dispute_id: str
    event_type: str
    payload_snapshot: Dict[str, Any]
    timestamp: str
    actor: str

class DisputeDetailResponse(BaseModel):
    dispute: RazorpayDispute
    payment: Optional[RazorpayPayment] = None
    evidence: Optional[EvidencePacket] = None
    decision: Optional[DecisionRecord] = None
    audit_events: List[AuditEventRecord] = Field(default_factory=list)
    features: Optional[Dict[str, Any]] = None
    time_remaining_hours: float = 0.0
