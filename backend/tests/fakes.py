from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FakeSimSystemClient:
    """Stands in for SimSystemClient in ingestion tests, so they don't need
    a real simulated-system server running. Filters by `since` the same way
    the real one does, so pipeline code gets exercised the same way it
    would against the real thing."""

    logs_by_service: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    metrics_by_service: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    deploys_by_service: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    services_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    inject_responses_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    reset_scenario_calls: list[str] = field(default_factory=list)
    inject_scenario_calls: list[str] = field(default_factory=list)

    def get_logs(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]:
        return self._filtered(self.logs_by_service.get(service, []), since)

    def get_metrics(self, service: str, since: datetime | None = None) -> list[dict[str, Any]]:
        return self._filtered(self.metrics_by_service.get(service, []), since)

    def get_deploys(self, service: str) -> list[dict[str, Any]]:
        return self.deploys_by_service.get(service, [])

    def get_service(self, service: str) -> dict[str, Any]:
        return self.services_by_name[service]

    def reset_scenario(self, scenario_id: str) -> None:
        self.reset_scenario_calls.append(scenario_id)

    def list_scenarios(self) -> list[dict[str, Any]]:
        return self.scenarios

    def inject_scenario(self, scenario_id: str) -> dict[str, Any]:
        self.inject_scenario_calls.append(scenario_id)
        return self.inject_responses_by_id[scenario_id]

    def close(self) -> None:
        pass

    @staticmethod
    def _filtered(entries: list[dict[str, Any]], since: datetime | None) -> list[dict[str, Any]]:
        if since is None:
            return entries
        return [entry for entry in entries if datetime.fromisoformat(entry["timestamp"]) >= since]
