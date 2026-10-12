import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ToolCallOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    tool_input_json: str
    tool_output_json: str | None
    is_side_effecting: bool
    status: str  # proposed | approved | rejected | executed | failed
    requested_at: datetime
    decided_at: datetime | None
    executed_at: datetime | None

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    id: uuid.UUID
    tool_call_id: uuid.UUID | None
    evidence_type: str  # log | metric | deploy | runbook
    summary: str
    raw_ref: str | None
    relevance_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HypothesisCitationOut(BaseModel):
    evidence_id: uuid.UUID

    model_config = {"from_attributes": True}


class HypothesisOut(BaseModel):
    id: uuid.UUID
    summary: str
    confidence: str  # low | medium | high
    reasoning: str | None
    created_at: datetime
    citations: list[HypothesisCitationOut] = []

    model_config = {"from_attributes": True}


class IncidentOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: str
    severity: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class IncidentDetailOut(IncidentOut):
    """Full incident state including evidence, hypotheses, and tool calls."""

    evidence: list[EvidenceOut] = []
    hypotheses: list[HypothesisOut] = []
    tool_calls: list[ToolCallOut] = []


class InvestigateResponse(BaseModel):
    """Returned by POST /incidents/{id}/investigate once the loop completes."""

    incident: IncidentDetailOut
    events_summary: list[str]  # human-readable event log for the UI


class AuditLogOut(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    actor: str  # system | user
    action: str
    detail_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunbookDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunbookSearchResultOut(BaseModel):
    document_title: str
    start_line: int
    end_line: int
    content: str
    distance: float
