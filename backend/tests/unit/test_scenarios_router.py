"""Tests for the scenario-proxy endpoints (Phase 8 groundwork).

The simulated system is monkeypatched the same way side_effecting.py's
tests do it: no real HTTP calls here. Live verification that the real
simulated system responds the way these tests assume was already done
by hand in Phase 2 and Phase 6.
"""

from collections.abc import Callable

import httpx
import pytest
from app.routers import scenarios
from fastapi.testclient import TestClient

from tests.fakes import FakeSimSystemClient


@pytest.fixture
def fake_sim_client(monkeypatch: pytest.MonkeyPatch) -> FakeSimSystemClient:
    fake = FakeSimSystemClient(
        scenarios=[
            {
                "id": "checkout-500s",
                "title": "Checkout returning 500s",
                "service": "checkout-service",
                "description": "A bad deploy ships without validating shipping_method.",
                "active": False,
            }
        ],
        inject_responses_by_id={
            "checkout-500s": {
                "scenario_id": "checkout-500s",
                "service": "checkout-service",
                "injected_at": "2026-10-13T00:00:00Z",
                "deploy": {
                    "sha": "abc1234",
                    "service": "checkout-service",
                    "message": "Add shipping method to checkout request schema",
                    "deployed_at": "2026-10-12T23:57:00Z",
                    "deployed_by": "ci-bot",
                },
            }
        },
    )
    monkeypatch.setattr(scenarios, "SimSystemClient", lambda base_url=None: fake)
    return fake


def test_list_scenarios_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/scenarios")
    assert response.status_code == 401


def test_inject_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/scenarios/checkout-500s/inject")
    assert response.status_code == 401


def test_reset_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/scenarios/checkout-500s/reset")
    assert response.status_code == 401


def test_list_scenarios_proxies_the_simulated_system(
    client: TestClient, register: Callable[[str, str], dict[str, str]], fake_sim_client: FakeSimSystemClient
) -> None:
    headers = register("alice@example.com")
    response = client.get("/api/scenarios", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "checkout-500s"


def test_inject_scenario_proxies_and_returns_the_deploy(
    client: TestClient, register: Callable[[str, str], dict[str, str]], fake_sim_client: FakeSimSystemClient
) -> None:
    headers = register("alice@example.com")
    response = client.post("/api/scenarios/checkout-500s/inject", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] == "checkout-500s"
    assert body["deploy"]["sha"] == "abc1234"
    assert fake_sim_client.inject_scenario_calls == ["checkout-500s"]


def test_reset_scenario_proxies_to_the_simulated_system(
    client: TestClient, register: Callable[[str, str], dict[str, str]], fake_sim_client: FakeSimSystemClient
) -> None:
    """Phase 11: added so the evaluation harness (and anything else that
    needs to restore a service to healthy between scenarios) has a real
    endpoint to call, instead of each scenario's deploy/log history just
    piling up forever across runs."""
    headers = register("alice@example.com")
    response = client.post("/api/scenarios/checkout-500s/reset", headers=headers)

    assert response.status_code == 204
    assert fake_sim_client.reset_scenario_calls == ["checkout-500s"]


def test_unknown_scenario_returns_the_sim_systems_404(
    client: TestClient, register: Callable[[str, str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_404(scenario_id: str) -> None:
        request = httpx.Request("POST", f"http://sim/scenarios/{scenario_id}/inject")
        response = httpx.Response(404, text="Unknown scenario: does-not-exist", request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    fake = FakeSimSystemClient()
    fake.inject_scenario = _raise_404  # type: ignore[method-assign]
    monkeypatch.setattr(scenarios, "SimSystemClient", lambda base_url=None: fake)

    headers = register("alice@example.com")
    response = client.post("/api/scenarios/does-not-exist/inject", headers=headers)
    assert response.status_code == 404


def test_simulated_system_unreachable_returns_502(
    client: TestClient, register: Callable[[str, str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_connect_error() -> None:
        raise httpx.ConnectError("Connection refused")

    class _BrokenClient:
        def list_scenarios(self) -> list[dict]:
            _raise_connect_error()

        def close(self) -> None:
            pass

    monkeypatch.setattr(scenarios, "SimSystemClient", lambda base_url=None: _BrokenClient())

    headers = register("alice@example.com")
    response = client.get("/api/scenarios", headers=headers)
    assert response.status_code == 502
