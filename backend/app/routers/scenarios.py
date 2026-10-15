"""Proxies the simulated system's scenario endpoints (spec §2 MVP item
#19: "demo scenario reviewers can trigger themselves"). The frontend
never talks to the simulated system directly, per the architecture
diagram in the README, so this is the one place that HTTP hop happens
for scenario listing/injection. Not incident-scoped: a scenario is
shared, global demo-system state, not owned by any one user or incident.

Phase 11 addition: /reset, so a scenario can be cleared back to healthy
without a deploy/log history pileup across repeated runs. The Phase 11
evaluation harness is what surfaced the gap: without this, consecutive
scenarios on the same service kept stacking deploy history, which once
caused a hypothesis to cite a stale, unrelated deploy (see
evaluation/README or docs/progress.md Phase 11 notes).
"""

import functools

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_current_user
from app.ingestion.sim_client import SimSystemClient
from app.models import User
from app.schemas import InjectScenarioResponse, ScenarioOut

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def _proxy_sim_system_errors(func):  # noqa: ANN001, ANN202 - tiny local decorator, not public API
    # functools.wraps matters here, not just for __name__/__doc__: FastAPI
    # reads the wrapped function's real parameter list (including the
    # Depends() defaults) via inspect.signature, which follows
    # __wrapped__. Without this, current_user's Depends() vanishes behind
    # this wrapper's generic (*args, **kwargs) and dependency injection
    # breaks.
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(exc.response.status_code, exc.response.text) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Simulated system unreachable: {exc}") from exc

    return wrapper


@router.get("", response_model=list[ScenarioOut])
@_proxy_sim_system_errors
def list_scenarios(current_user: User = Depends(get_current_user)) -> list[dict]:
    client = SimSystemClient()
    try:
        return client.list_scenarios()
    finally:
        client.close()


@router.post("/{scenario_id}/inject", response_model=InjectScenarioResponse)
@_proxy_sim_system_errors
def inject_scenario(scenario_id: str, current_user: User = Depends(get_current_user)) -> dict:
    client = SimSystemClient()
    try:
        return client.inject_scenario(scenario_id)
    finally:
        client.close()


@router.post("/{scenario_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
@_proxy_sim_system_errors
def reset_scenario(scenario_id: str, current_user: User = Depends(get_current_user)) -> None:
    client = SimSystemClient()
    try:
        client.reset_scenario(scenario_id)
    finally:
        client.close()
