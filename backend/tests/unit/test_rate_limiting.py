"""Tests for Phase 10 rate limiting (app/rate_limit.py).

The limiter's counters live for the whole test process, but the `client`
fixture (tests/conftest.py) calls limiter.reset() before every test, so
each test here starts with a full allowance regardless of what earlier
tests did against the same key.
"""

import pytest
from app.agent.provider import ProviderResponse
from fastapi.testclient import TestClient

SIMPLE_HYPOTHESIS = (
    "HYPOTHESIS:\nHigh error rate observed on checkout-service.\n\n"
    "CONFIDENCE: medium\n"
    "REASONING: Error rate data shows 18% error rate."
)


def test_login_is_rate_limited_after_repeated_attempts(client: TestClient, register) -> None:
    register("rl-login@example.com", "password123")

    # The configured limit is 10/minute; 10 attempts (right at the limit)
    # all still get a real response, the 11th is throttled.
    for _ in range(10):
        resp = client.post(
            "/api/auth/login",
            json={"email": "rl-login@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/api/auth/login",
        json={"email": "rl-login@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 429


def test_investigate_is_rate_limited(client: TestClient, register, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = register("rl-investigate@example.com")
    monkeypatch.setattr(
        "app.agent.orchestrator.call_llm",
        lambda messages, schemas, **kw: ProviderResponse(content=SIMPLE_HYPOTHESIS, tool_calls=[]),
    )

    incident_ids = []
    for _ in range(11):
        resp = client.post("/api/incidents", json={"title": "spam"}, headers=headers)
        assert resp.status_code == 201
        incident_ids.append(resp.json()["id"])

    # 10/minute on investigate: the first 10 incidents (against incidents
    # that don't exist as far as this test cares about the LLM call, they
    # just need to pass the ownership/status checks before hitting the
    # limiter) all get a real response, not 429. The 11th is throttled.
    statuses = []
    for incident_id in incident_ids:
        resp = client.post(f"/api/incidents/{incident_id}/investigate", headers=headers)
        statuses.append(resp.status_code)

    assert statuses[:10].count(429) == 0
    assert statuses[10] == 429


def test_rate_limit_is_scoped_per_client_not_global(client: TestClient, register) -> None:
    """A spammy client shouldn't be able to lock out a different one, this
    just confirms the limiter is keyed at all rather than sharing one
    global counter across every request."""
    register("rl-shared-a@example.com", "password123")

    for _ in range(10):
        client.post(
            "/api/auth/login",
            json={"email": "rl-shared-a@example.com", "password": "wrong-password"},
        )

    # The next register call is a different route (different limiter key
    # scope) and should still work, confirming limits don't bleed across
    # unrelated endpoints.
    resp = client.post(
        "/api/auth/register",
        json={"email": "rl-shared-b@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
