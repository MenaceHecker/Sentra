"""The one place an AuditLog row ever gets created (spec §7, §14 Phase 7).

Every entry is a plain INSERT. Nothing in this codebase ever updates or
deletes one, so the trail is append-only by construction, there's no
UPDATE/DELETE path to even accidentally wire up.

The design goal is that an investigation is fully reconstructable from
these rows alone, without needing to join back to tool_calls or
hypotheses: write_audit's detail snapshots the actual content (tool
input/output, hypothesis text, decision outcome) at the moment it
happened, not just an id pointing at a row that could theoretically
change later.
"""

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    incident_id: uuid.UUID,
    actor: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        incident_id=incident_id,
        actor=actor,
        action=action,
        detail_json=json.dumps(detail, default=str) if detail is not None else None,
    )
    db.add(entry)
    db.flush()
    return entry


def write_status_change(
    db: Session,
    incident_id: uuid.UUID,
    actor: str,
    old_status: str,
    new_status: str,
) -> AuditLog | None:
    """No-ops if the status didn't actually change, so callers can call
    this unconditionally after every place that sets incident.status
    without worrying about logging a no-op transition."""
    if old_status == new_status:
        return None
    return write_audit(db, incident_id, actor, "status_changed", {"from": old_status, "to": new_status})
