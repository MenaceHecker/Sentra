"""Incidents router.

Phase 5 additions:
  - GET /{id}     now returns IncidentDetailOut (evidence + hypotheses + tool calls)
  - POST /{id}/investigate  runs the agent loop and returns the result

Phase 6 additions:
  - POST /{id}/actions/{action_id}/approve  approves AND executes a proposed
    side-effecting call in one step (see app/tools/executor.py)
  - POST /{id}/actions/{action_id}/reject   rejects it, permanently, it can
    never be approved after this

Phase 7 additions:
  - GET /{id}/audit-log  every AuditLog row for this incident, oldest first

Phase 9 additions:
  - POST /{id}/investigate now streams over SSE instead of blocking for the
    whole investigation and returning one JSON blob at the end.

Phase 10 additions:
  - POST "" and POST /{id}/investigate are rate-limited (see app/rate_limit.py);
    investigate especially, since every call spends real LLM money.
"""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, selectinload
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.agent.orchestrator import ErrorEvent, HypothesisEvent, ToolCallEvent, run_investigation
from app.audit import write_audit, write_status_change
from app.db import get_db
from app.deps import get_current_user
from app.models import AuditLog, Hypothesis, Incident, ToolCall, User
from app.rate_limit import limiter
from app.schemas import AuditLogOut, IncidentCreate, IncidentDetailOut, IncidentOut, InvestigateResponse, ToolCallOut
from app.tools.executor import execute_approved_call

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _load_incident_detail(db: Session, incident_id: uuid.UUID, user_id: uuid.UUID) -> Incident:
    """Load an incident with all related data eager-loaded, enforcing ownership."""
    incident = (
        db.query(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.tool_calls),
            selectinload(Incident.hypotheses).selectinload(Hypothesis.citations),
        )
        .filter(Incident.id == incident_id)
        .first()
    )
    if incident is None or incident.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return incident


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_incident(
    request: Request,
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


def _tool_call_event_payload(event: ToolCallEvent) -> dict:
    return {
        "tool_call_id": str(event.tool_call_id),
        "tool_name": event.tool_name,
        "tool_input": event.tool_input,
        "status": event.status,
        "output_summary": event.output_summary,
    }


def _hypothesis_event_payload(event: HypothesisEvent) -> dict:
    return {
        "hypothesis_id": str(event.hypothesis_id),
        "summary": event.summary,
        "confidence": event.confidence,
        "reasoning": event.reasoning,
        "proposed_actions": event.proposed_actions,
    }


@router.post("/{incident_id}/investigate")
@limiter.limit("10/minute")
async def investigate_incident(
    request: Request,
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    """Streams the agent investigation loop for an incident over SSE.

    One "tool_call" event per tool call and one "hypothesis" event when the
    model produces one, both as they happen rather than all at once at the
    end. An "error" event if a step fails. Always ends with a "done" event
    carrying the fully reloaded incident plus the same events_summary the
    old synchronous response used to return, so the client has one place to
    get the authoritative final state without a separate GET.

    Errors are reported in-band as "error" events, not as an HTTP error
    status: the response is already committed to 200 by the time streaming
    starts, so there's no HTTP status left to carry a failure that happens
    partway through.

    run_investigation is a plain sync generator that does blocking HTTP
    calls (to the LLM, to the simulated system) between yields.
    iterate_in_threadpool runs each step in a worker thread so the event
    loop stays free to actually flush each chunk to the client as it's
    produced, instead of buffering everything until the whole loop finishes.
    """
    # Ownership check (returns 404, not 403, to avoid confirming IDs exist)
    incident = db.get(Incident, incident_id)
    if incident is None or incident.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    if incident.status in ("resolved", "closed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Incident is already {incident.status}, create a new incident to re-investigate.",
        )

    async def event_stream():
        events_summary: list[str] = []

        async for event in iterate_in_threadpool(run_investigation(db, incident)):
            if isinstance(event, ToolCallEvent):
                side = " [side-effecting, awaiting approval]" if event.status == "proposed" else ""
                events_summary.append(f"tool_call: {event.tool_name}{side}")
                yield {"event": "tool_call", "data": json.dumps(_tool_call_event_payload(event))}
            elif isinstance(event, HypothesisEvent):
                events_summary.append(
                    f"hypothesis: confidence={event.confidence} proposed_actions={len(event.proposed_actions)}"
                )
                yield {"event": "hypothesis", "data": json.dumps(_hypothesis_event_payload(event))}
            elif isinstance(event, ErrorEvent):
                events_summary.append(f"error: {event.message}")
                yield {"event": "error", "data": json.dumps({"message": event.message})}

        detail = _load_incident_detail(db, incident_id, current_user.id)
        done = InvestigateResponse(incident=IncidentDetailOut.model_validate(detail), events_summary=events_summary)
        yield {"event": "done", "data": done.model_dump_json()}

    return EventSourceResponse(event_stream())


def _get_proposed_action(db: Session, incident_id: uuid.UUID, action_id: uuid.UUID) -> ToolCall:
    """Looks up a proposed side-effecting ToolCall scoped to this incident.
    Same 404-not-403 reasoning as everywhere else: a 400/403 would confirm
    the action exists at all, even for the wrong incident."""
    call = db.get(ToolCall, action_id)
    if call is None or call.incident_id != incident_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposed action not found")
    if not call.is_side_effecting:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This tool call was never a proposal, there's nothing to decide"
        )
    if call.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This action was already decided (status: {call.status})")
    return call


def _other_pending_actions_remain(db: Session, incident_id: uuid.UUID, deciding_action_id: uuid.UUID) -> bool:
    return (
        db.query(ToolCall)
        .filter(
            ToolCall.incident_id == incident_id,
            ToolCall.id != deciding_action_id,
            ToolCall.is_side_effecting.is_(True),
            ToolCall.status == "proposed",
        )
        .first()
        is not None
    )


@router.post("/{incident_id}/actions/{action_id}/approve", response_model=ToolCallOut)
def approve_action(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ToolCall:
    """Approves a proposed side-effecting action and executes it immediately
    in the same request. There's no separate "execute" step: spec Section
    10 only defines approve/reject, and the Phase 6 checkpoint is that an
    approved rollback actually changes things, not that it gets queued for
    something else to run later.
    """
    incident = db.get(Incident, incident_id)
    if incident is None or incident.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    call = _get_proposed_action(db, incident_id, action_id)

    call.status = "approved"
    call.decided_at = datetime.now(UTC)
    call.decided_by_user_id = current_user.id
    db.flush()

    execute_approved_call(db, call)

    write_audit(
        db,
        incident_id,
        "user",
        "action_approved",
        {
            "tool_call_id": str(call.id),
            "tool_name": call.tool_name,
            "tool_input": json.loads(call.tool_input_json),
            "decided_by_user_id": str(current_user.id),
            "outcome": call.status,
            "output": json.loads(call.tool_output_json) if call.tool_output_json else None,
        },
    )

    old_status = incident.status
    if not _other_pending_actions_remain(db, incident_id, call.id):
        if call.status == "executed":
            incident.status = "resolved"
            incident.resolved_at = datetime.now(UTC)
        else:
            # Approved, but execution failed. Nothing to action on anymore,
            # but the incident is not resolved, it needs another look.
            incident.status = "hypothesis_ready"
    write_status_change(db, incident_id, "user", old_status, incident.status)

    db.commit()
    db.refresh(call)
    return call


@router.post("/{incident_id}/actions/{action_id}/reject", response_model=ToolCallOut)
def reject_action(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ToolCall:
    """Rejects a proposed action. Permanently: a rejected call's status
    never becomes "proposed" again, there's no undo endpoint. It never
    executes, full stop, regardless of what anything else requests later.
    """
    incident = db.get(Incident, incident_id)
    if incident is None or incident.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    call = _get_proposed_action(db, incident_id, action_id)

    call.status = "rejected"
    call.decided_at = datetime.now(UTC)
    call.decided_by_user_id = current_user.id

    write_audit(
        db,
        incident_id,
        "user",
        "action_rejected",
        {
            "tool_call_id": str(call.id),
            "tool_name": call.tool_name,
            "tool_input": json.loads(call.tool_input_json),
            "decided_by_user_id": str(current_user.id),
        },
    )

    old_status = incident.status
    if not _other_pending_actions_remain(db, incident_id, call.id):
        incident.status = "hypothesis_ready"
    write_status_change(db, incident_id, "user", old_status, incident.status)

    db.commit()
    db.refresh(call)
    return call


@router.get("/{incident_id}/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    """Every audit entry for this incident, oldest first, so reading top to
    bottom tells the whole story: investigation started, each tool call
    with its real input and output, the hypothesis that came out of it,
    and every human decision after that. This is the Phase 7 checkpoint:
    an investigation should be reconstructable from this list alone.
    """
    incident = db.get(Incident, incident_id)
    if incident is None or incident.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    return db.query(AuditLog).filter(AuditLog.incident_id == incident_id).order_by(AuditLog.created_at.asc()).all()
