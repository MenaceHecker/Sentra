"""Incidents router.

Phase 5 additions:
  - GET /{id}     now returns IncidentDetailOut (evidence + hypotheses + tool calls)
  - POST /{id}/investigate  runs the agent loop synchronously and returns the result

Phase 9 will convert POST /{id}/investigate to SSE streaming.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models import Incident, User
from app.schemas import IncidentCreate, IncidentDetailOut, IncidentOut, InvestigateResponse

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _load_incident_detail(db: Session, incident_id: uuid.UUID, user_id: uuid.UUID) -> Incident:
    """Load an incident with all related data eager-loaded, enforcing ownership."""
    incident = (
        db.query(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.tool_calls),
            selectinload(Incident.hypotheses).selectinload("citations"),
        )
        .filter(Incident.id == incident_id)
        .first()
    )
    if incident is None or incident.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return incident


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Incident:
    incident = Incident(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Incident]:
    return db.query(Incident).filter(Incident.user_id == current_user.id).order_by(Incident.created_at.desc()).all()


@router.get("/{incident_id}", response_model=IncidentDetailOut)
def get_incident(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Incident:
    return _load_incident_detail(db, incident_id, current_user.id)


@router.post("/{incident_id}/investigate", response_model=InvestigateResponse)
def investigate_incident(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvestigateResponse:
    """Run the agent investigation loop for an incident.

    Synchronous for now (Phase 5).  Phase 9 will add SSE streaming.

    The incident must belong to the requesting user and must be in a state
    where investigation makes sense (investigating or hypothesis_ready for
    follow-up questions).  Once a loop is running, the endpoint returns only
    after the model is done — typically 10-30 seconds depending on the number
    of tool calls and LLM latency.
    """
    from app.agent.orchestrator import ErrorEvent, HypothesisEvent, ToolCallEvent, run_investigation

    # Ownership check (returns 404, not 403, to avoid confirming IDs exist)
    incident = db.get(Incident, incident_id)
    if incident is None or incident.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    if incident.status in ("resolved", "closed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Incident is already {incident.status} — create a new incident to re-investigate.",
        )

    # Run the investigation loop (generator exhausted synchronously here)
    events_summary: list[str] = []
    error_message: str | None = None

    for event in run_investigation(db, incident):
        if isinstance(event, ToolCallEvent):
            side = " [side-effecting, awaiting approval]" if event.status == "proposed" else ""
            events_summary.append(f"tool_call: {event.tool_name}{side}")
        elif isinstance(event, HypothesisEvent):
            events_summary.append(
                f"hypothesis: confidence={event.confidence} "
                f"proposed_actions={len(event.proposed_actions)}"
            )
        elif isinstance(event, ErrorEvent):
            error_message = event.message
            events_summary.append(f"error: {event.message}")

    if error_message and not events_summary[:-1]:  # only the error event
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Investigation failed: {error_message}")

    # Reload with full detail for the response
    detail = _load_incident_detail(db, incident_id, current_user.id)
    return InvestigateResponse(incident=detail, events_summary=events_summary)
