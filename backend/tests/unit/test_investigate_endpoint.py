"""Integration tests for the investigate endpoint (Phase 5).

Tests the full HTTP path: POST /api/incidents/{id}/investigate returns
the expected schema and has the correct incident state.

The LLM provider is monkeypatched so no real API call is made.
"""

import pytest
from fastapi.testclient import TestClient

from app.agent.provider import ProviderResponse
from app.seed import seed_services


SIMPLE_HYPOTHESIS = (
    "HYPOTHESIS:\nHigh error rate observed on checkout-service.\n\n"
    "CONFIDENCE: medium\n"
    "REASONING: Error rate data shows 18% error rate.\n\n"
    "PROPOSED_ACTIONS:\nnone"
)


@pytest.fixture(autouse=True)
def _seed(db_session) -> None:
    seed_services(db_session)


def test_investigate_returns_hypothesis(
    client: TestClient, register, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = register("inv-test@example.com")

    # Create incident
    resp = client.post(
        "/api/incidents",
        json={"title": "Checkout returning 500s"},
        headers=headers,
    )
    assert resp.status_code == 201
    incident_id = resp.json()["id"]

    # Monkeypatch the LLM call
    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=SIMPLE_HYPOTHESIS, tool_calls=[]),
    )

    resp = client.post(f"/api/incidents/{incident_id}/investigate", headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["incident"]["status"] == "hypothesis_ready"
    assert len(data["incident"]["hypotheses"]) == 1
    hyp = data["incident"]["hypotheses"][0]
    assert hyp["confidence"] == "medium"
    assert "checkout-service" in hyp["summary"]
    assert "events_summary" in data


def test_investigate_unknown_incident_returns_404(
    client: TestClient, register, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = register("inv-404@example.com")
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = client.post(f"/api/incidents/{fake_id}/investigate", headers=headers)
    assert resp.status_code == 404


def test_investigate_other_users_incident_returns_404(
    client: TestClient, register, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers_a = register("inv-a@example.com")
    headers_b = register("inv-b@example.com")

    resp = client.post("/api/incidents", json={"title": "A's incident"}, headers=headers_a)
    incident_id = resp.json()["id"]

    resp = client.post(f"/api/incidents/{incident_id}/investigate", headers=headers_b)
    assert resp.status_code == 404


def test_investigate_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/incidents/00000000-0000-0000-0000-000000000000/investigate")
    assert resp.status_code == 401


def test_get_incident_detail_includes_hypotheses_and_tool_calls(
    client: TestClient, register, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = register("inv-detail@example.com")

    resp = client.post("/api/incidents", json={"title": "Payments timeout"}, headers=headers)
    incident_id = resp.json()["id"]

    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=SIMPLE_HYPOTHESIS, tool_calls=[]),
    )
    client.post(f"/api/incidents/{incident_id}/investigate", headers=headers)

    resp = client.get(f"/api/incidents/{incident_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "hypotheses" in data
    assert "evidence" in data
    assert "tool_calls" in data
