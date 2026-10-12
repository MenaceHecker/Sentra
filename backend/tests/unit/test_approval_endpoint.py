"""HTTP-level tests for the approve/reject endpoints (Phase 6).

The simulated system is monkeypatched the same way the orchestrator tests
monkeypatch the LLM: no real HTTP calls to it from these tests. Live
verification that execute_approved_call actually changes something in a
real running simulated system was done by hand, same as the Gemini
integration.
"""

from collections.abc import Callable

import pytest
from app.models import ToolCall
from app.seed import seed_services
from app.tools import side_effecting
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fakes import FakeSimSystemClient


@pytest.fixture(autouse=True)
def _seed(db_session: Session) -> None:
    seed_services(db_session)


@pytest.fixture(autouse=True)
def _fake_sim_client(monkeypatch: pytest.MonkeyPatch) -> FakeSimSystemClient:
    fake = FakeSimSystemClient(
        services_by_name={"checkout-service": {"name": "checkout-service", "active_scenario_id": "checkout-500s"}}
    )
    monkeypatch.setattr(side_effecting, "SimSystemClient", lambda base_url=None: fake)
    return fake


def _make_incident_with_proposed_action(
    client: TestClient, db_session: Session, headers: dict[str, str], tool_name: str = "rollback_deploy"
) -> tuple[str, str]:
    """Creates an incident via the real API, then writes a proposed
    side-effecting ToolCall for it directly, same end state an
    investigation would leave, without running one."""
    resp = client.post("/api/incidents", json={"title": "Checkout returning 500s"}, headers=headers)
    incident_id = resp.json()["id"]

    call = ToolCall(
        incident_id=incident_id,
        tool_name=tool_name,
        tool_input_json='{"service": "checkout-service", "target_sha": "a1", "reason": "bad deploy"}',
        is_side_effecting=True,
        status="proposed",
    )
    db_session.add(call)
    db_session.commit()
    return incident_id, str(call.id)


_FAKE_UUID_PATH = "00000000-0000-0000-0000-000000000000/actions/00000000-0000-0000-0000-000000000000"


def test_approve_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/incidents/{_FAKE_UUID_PATH}/approve")
    assert response.status_code == 401


def test_reject_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/incidents/{_FAKE_UUID_PATH}/reject")
    assert response.status_code == 401


def test_approve_on_someone_elses_incident_returns_404(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    owner_headers = register("owner@example.com")
    other_headers = register("other@example.com")
    incident_id, action_id = _make_incident_with_proposed_action(client, db_session, owner_headers)

    response = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=other_headers)
    assert response.status_code == 404


def test_approve_unknown_action_returns_404(client: TestClient, register: Callable[[str, str], dict[str, str]]) -> None:
    headers = register("alice@example.com")
    resp = client.post("/api/incidents", json={"title": "x"}, headers=headers)
    incident_id = resp.json()["id"]

    response = client.post(
        f"/api/incidents/{incident_id}/actions/00000000-0000-0000-0000-000000000000/approve", headers=headers
    )
    assert response.status_code == 404


def test_cannot_approve_a_read_only_tool_call(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    headers = register("alice@example.com")
    incident_id, _ = _make_incident_with_proposed_action(client, db_session, headers)

    read_only_call = ToolCall(
        incident_id=incident_id,
        tool_name="get_service_status",
        tool_input_json='{"service": "checkout-service"}',
        is_side_effecting=False,
        status="executed",
    )
    db_session.add(read_only_call)
    db_session.commit()

    response = client.post(f"/api/incidents/{incident_id}/actions/{read_only_call.id}/approve", headers=headers)
    assert response.status_code == 400


def test_approve_executes_and_resolves_the_incident(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    headers = register("alice@example.com")
    incident_id, action_id = _make_incident_with_proposed_action(client, db_session, headers)

    response = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "executed"
    assert body["decided_at"] is not None
    assert body["executed_at"] is not None

    incident = client.get(f"/api/incidents/{incident_id}", headers=headers).json()
    assert incident["status"] == "resolved"
    assert incident["resolved_at"] is not None


def test_approve_twice_is_rejected_the_second_time(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    headers = register("alice@example.com")
    incident_id, action_id = _make_incident_with_proposed_action(client, db_session, headers)

    first = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=headers)
    assert first.status_code == 200

    second = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=headers)
    assert second.status_code == 409


def test_reject_leaves_the_incident_at_hypothesis_ready_and_blocks_future_approval(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    headers = register("alice@example.com")
    incident_id, action_id = _make_incident_with_proposed_action(client, db_session, headers)

    response = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/reject", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    incident = client.get(f"/api/incidents/{incident_id}", headers=headers).json()
    assert incident["status"] == "hypothesis_ready"

    # Rejected is permanent: it can never be approved after the fact.
    approve_after_reject = client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=headers)
    assert approve_after_reject.status_code == 409


def test_incident_stays_action_pending_while_another_proposal_is_still_open(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    from app.models import Incident

    headers = register("alice@example.com")
    incident_id, first_action_id = _make_incident_with_proposed_action(client, db_session, headers)

    second_call = ToolCall(
        incident_id=incident_id,
        tool_name="post_status_update",
        tool_input_json='{"message": "investigating"}',
        is_side_effecting=True,
        status="proposed",
    )
    db_session.add(second_call)
    # A real investigation would have already set this; set it directly
    # here since this test bypasses run_investigation entirely.
    db_session.query(Incident).filter(Incident.id == incident_id).update({"status": "action_pending"})
    db_session.commit()

    response = client.post(f"/api/incidents/{incident_id}/actions/{first_action_id}/approve", headers=headers)
    assert response.status_code == 200

    incident = client.get(f"/api/incidents/{incident_id}", headers=headers).json()
    assert incident["status"] == "action_pending"  # second_call is still proposed


def test_approval_writes_an_audit_log_entry(
    client: TestClient, db_session: Session, register: Callable[[str, str], dict[str, str]]
) -> None:
    from app.models import AuditLog

    headers = register("alice@example.com")
    incident_id, action_id = _make_incident_with_proposed_action(client, db_session, headers)

    client.post(f"/api/incidents/{incident_id}/actions/{action_id}/approve", headers=headers)

    entries = db_session.query(AuditLog).filter(AuditLog.incident_id == incident_id).all()
    assert any(entry.action == "action_approved" for entry in entries)
