from datetime import datetime
from typing import Any, Protocol

import httpx

from app.config import get_settings


class SimSystemClientProtocol(Protocol):
    """What the ingestion pipeline actually needs from a sim-system client.
    Tests implement this with an in-memory fake instead of hitting a real
    HTTP server."""

    def get_logs(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]: ...
    def get_metrics(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]: ...
    def get_deploys(self, service: str) -> list[dict[str, Any]]: ...


class SimSystemClient:
    """Thin sync HTTP client over the simulated system's API. Kept
    deliberately simple and synchronous so the ingestion pipeline is easy
    to unit test with a fake in place of this, no async test machinery
    needed. The background loop that uses this in main.py runs it in a
    thread so it doesn't block the event loop."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._client = httpx.Client(base_url=(base_url or settings.sim_system_base_url).rstrip("/"), timeout=10.0)

    def close(self) -> None:
        self._client.close()

    def list_services(self) -> list[dict[str, Any]]:
        return self._get("/services")

    def get_logs(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 2000}
        if since is not None:
            params["start_time"] = since.isoformat()
        return self._get(f"/services/{service}/logs", params=params)

    def get_metrics(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 5000}
        if since is not None:
            params["start_time"] = since.isoformat()
        return self._get(f"/services/{service}/metrics", params=params)

    def get_deploys(self, service: str) -> list[dict[str, Any]]:
        return self._get(f"/services/{service}/deploys")

    def get_service(self, service: str) -> dict[str, Any]:
        """Single-service detail, including active_scenario_id. Used by the
        approval workflow to find what's actually degrading a service
        before trying to clear it (see app/tools/side_effecting.py)."""
        response = self._client.get(f"/services/{service}")
        response.raise_for_status()
        return response.json()

    def reset_scenario(self, scenario_id: str) -> None:
        """Clears whatever failure scenario is active, the only real lever
        the simulated system exposes for an approved action to pull."""
        response = self._client.post(f"/scenarios/{scenario_id}/reset")
        response.raise_for_status()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()
