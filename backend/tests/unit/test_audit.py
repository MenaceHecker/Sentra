import json

from app.audit import write_audit, write_status_change
from app.models import AuditLog, Incident, User
from sqlalchemy.orm import Session


def _make_incident(db_session: Session) -> Incident:
    user = User(email="oncall@example.com", hashed_password="x", display_name="On Call")
    db_session.add(user)
    db_session.flush()
    incident = Incident(user_id=user.id, title="Checkout returning 500s")
    db_session.add(incident)
    db_session.flush()
    return incident


def test_write_audit_persists_actor_action_and_detail(db_session: Session) -> None:
    incident = _make_incident(db_session)

    entry = write_audit(db_session, incident.id, "system", "tool_call", {"tool_name": "query_logs"})

    assert entry.id is not None
    assert entry.actor == "system"
    assert entry.action == "tool_call"
    assert json.loads(entry.detail_json) == {"tool_name": "query_logs"}


def test_write_audit_allows_no_detail(db_session: Session) -> None:
    incident = _make_incident(db_session)
    entry = write_audit(db_session, incident.id, "user", "action_rejected")
    assert entry.detail_json is None


def test_write_status_change_records_from_and_to(db_session: Session) -> None:
    incident = _make_incident(db_session)

    entry = write_status_change(db_session, incident.id, "system", "investigating", "hypothesis_ready")

    assert entry is not None
    assert entry.action == "status_changed"
    assert json.loads(entry.detail_json) == {"from": "investigating", "to": "hypothesis_ready"}


def test_write_status_change_is_a_noop_when_status_is_unchanged(db_session: Session) -> None:
    incident = _make_incident(db_session)

    entry = write_status_change(db_session, incident.id, "system", "investigating", "investigating")

    assert entry is None
    assert db_session.query(AuditLog).filter(AuditLog.incident_id == incident.id).count() == 0
