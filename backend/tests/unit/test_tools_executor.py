import dataclasses
import json

import pytest
from app.models import Incident, MetricPoint, Service, User
from app.seed import seed_services
from app.tools.executor import call_tool
from app.tools.registry import TOOLS
from sqlalchemy.orm import Session


def _make_incident(db_session: Session) -> Incident:
    user = User(email="oncall@example.com", hashed_password="x", display_name="On Call")
    db_session.add(user)
    db_session.flush()

    incident = Incident(user_id=user.id, title="Checkout returning 500s")
    db_session.add(incident)
    db_session.flush()
    return incident


def test_read_only_tool_executes_immediately(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    call = call_tool(db_session, incident.id, "get_service_status", {"service": "checkout-service"})

    assert call.status == "executed"
    assert call.is_side_effecting is False
    assert call.executed_at is not None
    output = json.loads(call.tool_output_json)
    assert output["status"] == "unknown"  # no metrics ingested in this test


def test_read_only_tool_output_reflects_real_data(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    service = db_session.query(Service).filter(Service.name == "checkout-service").one()
    db_session.add(
        MetricPoint(service_id=service.id, timestamp=incident.created_at, metric_name="error_rate", value=0.4)
    )
    db_session.commit()

    call = call_tool(db_session, incident.id, "get_service_status", {"service": "checkout-service"})

    output = json.loads(call.tool_output_json)
    assert output["status"] == "degraded"


def test_side_effecting_tool_is_only_proposed_never_executed(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    # Tool is a frozen dataclass, so swap the whole registry entry for one
    # with a spy in place of `run`. If the executor ever stopped
    # short-circuiting before tool.run for a side-effecting tool, this spy
    # firing is what would catch it.
    was_called = False

    def _spy(db, params):
        nonlocal was_called
        was_called = True
        return {"action": "restart_service"}

    monkeypatch.setitem(TOOLS, "restart_service", dataclasses.replace(TOOLS["restart_service"], run=_spy))

    call = call_tool(
        db_session, incident.id, "restart_service", {"service": "checkout-service", "reason": "error spike"}
    )

    assert call.status == "proposed"
    assert call.is_side_effecting is True
    assert call.executed_at is None
    assert call.tool_output_json is None
    assert was_called is False


def test_every_side_effecting_tool_stays_proposed(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    cases = [
        ("restart_service", {"service": "checkout-service", "reason": "r"}),
        ("rollback_deploy", {"service": "checkout-service", "target_sha": "abc", "reason": "r"}),
        ("post_status_update", {"message": "investigating"}),
    ]
    for tool_name, tool_input in cases:
        call = call_tool(db_session, incident.id, tool_name, tool_input)
        assert call.status == "proposed", f"{tool_name} should stay proposed"
        assert call.tool_output_json is None


def test_unknown_tool_is_persisted_as_failed(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    call = call_tool(db_session, incident.id, "delete_everything", {})

    assert call.status == "failed"
    assert call.tool_name == "delete_everything"
    assert "unknown tool" in json.loads(call.tool_output_json)["error"]


def test_invalid_input_is_persisted_as_failed_with_raw_input_preserved(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    call = call_tool(db_session, incident.id, "get_metrics", {"service": "checkout-service"})  # missing metric_name

    assert call.status == "failed"
    # The raw (invalid) input is still exactly what was recorded, not silently dropped.
    assert json.loads(call.tool_input_json) == {"service": "checkout-service"}


def test_a_failing_read_only_tool_is_recorded_not_raised(db_session: Session) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    call = call_tool(db_session, incident.id, "query_logs", {"service": "does-not-exist"})

    assert call.status == "failed"
    assert "Unknown service" in json.loads(call.tool_output_json)["error"]


def test_every_tool_call_is_persisted_before_it_runs(db_session: Session) -> None:
    """Even a call that will fail validation shows up in the incident's
    tool_calls, since the point is an auditable trail of every attempt."""
    seed_services(db_session)
    incident = _make_incident(db_session)

    call_tool(db_session, incident.id, "get_metrics", {"service": "checkout-service"})

    assert len(incident.tool_calls) == 1


def test_execute_approved_call_runs_the_real_implementation(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6: once a human approves, execute_approved_call is what
    actually runs the side-effecting tool, unlike call_tool which stops
    at "proposed" for these."""
    from app.tools import side_effecting
    from app.tools.executor import execute_approved_call

    from tests.fakes import FakeSimSystemClient

    fake_client = FakeSimSystemClient(
        services_by_name={"checkout-service": {"name": "checkout-service", "active_scenario_id": "checkout-500s"}}
    )
    monkeypatch.setattr(side_effecting, "SimSystemClient", lambda base_url=None: fake_client)

    seed_services(db_session)
    incident = _make_incident(db_session)
    call = call_tool(
        db_session, incident.id, "rollback_deploy", {"service": "checkout-service", "target_sha": "a1", "reason": "r"}
    )
    assert call.status == "proposed"  # sanity check: call_tool itself never runs this

    execute_approved_call(db_session, call)

    assert call.status == "executed"
    assert call.executed_at is not None
    output = json.loads(call.tool_output_json)
    assert output["reset_scenario"] is True
    assert fake_client.reset_scenario_calls == ["checkout-500s"]


def test_execute_approved_call_records_failure_instead_of_raising(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tools import side_effecting
    from app.tools.executor import execute_approved_call

    def _broken_client(base_url: str | None = None):
        raise ConnectionError("simulated system unreachable")

    monkeypatch.setattr(side_effecting, "SimSystemClient", _broken_client)

    seed_services(db_session)
    incident = _make_incident(db_session)
    call = call_tool(
        db_session, incident.id, "rollback_deploy", {"service": "checkout-service", "target_sha": "a1", "reason": "r"}
    )

    execute_approved_call(db_session, call)

    assert call.status == "failed"
    assert "simulated system unreachable" in json.loads(call.tool_output_json)["error"]
