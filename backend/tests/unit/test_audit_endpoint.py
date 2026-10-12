"""Tests for the audit-log endpoints (Phase 7).

test_investigation_is_fully_reconstructable_from_audit_log_alone is the
actual Phase 7 checkpoint: read nothing but the audit log entries and be
able to tell the whole story of an investigation.
"""

import json
from collections.abc import Callable

import pytest
from app.agent.provider import ProviderResponse
from app.models import ToolCall
from app.seed import seed_services
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_FAKE_UUID = "00000000-0000-0000-0000-000000000000"

GOOD_HYPOTHESIS = (
    "HYPOTHESIS:\nThe error spike followed deploy a1b2c3 by three minutes.\n\n"
    "CONFIDENCE: high\n"
    "REASONING: Strong temporal correlation; runbook confirms this pattern."
)


@pytest.fixture(autouse=True)
def _seed(db_session: Session) -> None:
    seed_services(db_session)


def test_per_incident_audit_log_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/api/incidents/{_FAKE_UUID}/audit-log")
    assert response.status_code == 401


def test_per_incident_audit_log_scoped_to_owner(
    client: TestClient, register: Callable[[str, str], dict[str, str]]
) -> None:
    owner_headers = register("owner@example.com")
    other_headers = register("other@example.com")
    incident_id = client.post("/api/incidents", json={"title": "x"}, headers=owner_headers).json()["id"]

    response = client.get(f"/api/incidents/{incident_id}/audit-log", headers=other_headers)
    assert response.status_code == 404


def test_global_audit_log_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/audit-log")
    assert response.status_code == 401


def test_global_audit_log_is_scoped_to_the_current_user(
    client: TestClient, register: Callable[[str, str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    alice_headers = register("alice@example.com")
    bob_headers = register("bob@example.com")

    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=GOOD_HYPOTHESIS, tool_calls=[]),
    )

    alice_incident = client.post("/api/incidents", json={"title": "Alice's incident"}, headers=alice_headers).json()
    client.post(f"/api/incidents/{alice_incident['id']}/investigate", headers=alice_headers)

    bob_log = client.get("/api/audit-log", headers=bob_headers).json()
    assert bob_log == []

    alice_log = client.get("/api/audit-log", headers=alice_headers).json()
    assert len(alice_log) > 0
    assert all(entry["incident_id"] == alice_incident["id"] for entry in alice_log)


def test_global_audit_log_filters_by_incident_id_and_action(
    client: TestClient, register: Callable[[str, str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = register("alice@example.com")
    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=GOOD_HYPOTHESIS, tool_calls=[]),
    )

    first = client.post("/api/incidents", json={"title": "First"}, headers=headers).json()
    second = client.post("/api/incidents", json={"title": "Second"}, headers=headers).json()
    client.post(f"/api/incidents/{first['id']}/investigate", headers=headers)
    client.post(f"/api/incidents/{second['id']}/investigate", headers=headers)

    by_incident = client.get(f"/api/audit-log?incident_id={first['id']}", headers=headers).json()
    assert len(by_incident) > 0
    assert all(entry["incident_id"] == first["id"] for entry in by_incident)

    by_action = client.get("/api/audit-log?action=hypothesis_generated", headers=headers).json()
    assert len(by_action) == 2  # one per incident
    assert all(entry["action"] == "hypothesis_generated" for entry in by_action)


def test_investigation_is_fully_reconstructable_from_audit_log_alone(
    client: TestClient,
    db_session: Session,
    register: Callable[[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = register("alice@example.com")

    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=GOOD_HYPOTHESIS, tool_calls=[]),
    )

    incident = client.post("/api/incidents", json={"title": "Checkout returning 500s"}, headers=headers).json()
    client.post(f"/api/incidents/{incident['id']}/investigate", headers=headers)

    # A second, independent side-effecting proposal, decided by hand (not
    # via the LLM loop) so the test also exercises the decision entries
    # without depending on the model proposing one natively.
    extra_call = ToolCall(
        incident_id=incident["id"],
        tool_name="post_status_update",
        tool_input_json='{"message": "investigating"}',
        is_side_effecting=True,
        status="proposed",
    )
    db_session.add(extra_call)
    db_session.commit()
    client.post(f"/api/incidents/{incident['id']}/actions/{extra_call.id}/reject", headers=headers)

    log = client.get(f"/api/incidents/{incident['id']}/audit-log", headers=headers).json()
    actions = [entry["action"] for entry in log]

    # The story, start to finish, readable purely from this list:
    assert "investigation_started" in actions
    assert "hypothesis_generated" in actions
    assert "status_changed" in actions
    assert "action_rejected" in actions

    # Chronological order: created_at strictly non-decreasing.
    timestamps = [entry["created_at"] for entry in log]
    assert timestamps == sorted(timestamps)

    # The hypothesis entry alone carries enough to know what was concluded,
    # no join back to the hypotheses table required.
    hypothesis_entry = next(entry for entry in log if entry["action"] == "hypothesis_generated")
    detail = json.loads(hypothesis_entry["detail_json"])
    assert detail["confidence"] == "high"
    assert "error spike" in detail["summary"]
    assert "temporal correlation" in detail["reasoning"]

    # The rejection entry alone names the tool and its input, no join back
    # to tool_calls required either.
    rejection_entry = next(entry for entry in log if entry["action"] == "action_rejected")
    rejection_detail = json.loads(rejection_entry["detail_json"])
    assert rejection_detail["tool_name"] == "post_status_update"
    assert rejection_detail["tool_input"] == {"message": "investigating"}
