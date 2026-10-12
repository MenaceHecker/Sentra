"""Global audit log (spec §4 Page 5, §10).

The per-incident view lives at GET /api/incidents/{id}/audit-log instead
(app/routers/incidents.py), since that's where ownership is naturally
checked. This one spans every incident the current user owns, which is
why it joins through Incident for the ownership filter rather than
trusting a user-supplied incident_id: audit_log has no user_id column of
its own, by design, an entry belongs to an incident, not directly to a
user.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import AuditLog, Incident, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    incident_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, description="Exact match, e.g. action_approved, tool_call"),
    limit: int = Query(default=200, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    query = (
        db.query(AuditLog)
        .join(Incident, AuditLog.incident_id == Incident.id)
        .filter(Incident.user_id == current_user.id)
    )

    if incident_id is not None:
        query = query.filter(AuditLog.incident_id == incident_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)

    return query.order_by(AuditLog.created_at.desc()).limit(limit).all()
