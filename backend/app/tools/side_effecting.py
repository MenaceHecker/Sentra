from sqlalchemy.orm import Session

from app.ingestion.sim_client import SimSystemClient
from app.tools.schemas import PostStatusUpdateInput, RestartServiceInput, RollbackDeployInput

# These only ever run from app/tools/executor.py's execute_approved_call,
# once a human has approved the proposal this function's output
# represents. Before that, call_tool() never invokes them, see Section 8
# rule 3. SimSystemClient is imported at module level (not inside the
# functions) so tests can monkeypatch app.tools.side_effecting.SimSystemClient
# with a fake, same pattern used elsewhere in this codebase, without any
# of these functions needing a third parameter that would break the
# uniform Tool.run(db, params) calling convention.


def _reset_active_scenario_for_service(service: str) -> dict:
    """The simulated system's only real remediation lever is clearing
    whatever failure scenario is currently injected on a service. Both
    restart_service and rollback_deploy use this: in this simulated world
    there's no meaningful difference between "restart fixed it" and
    "rollback fixed it", there's just "the injected failure is still
    there" or "it's gone now". Reports honestly if there was nothing to
    reset, rather than claiming success either way."""
    client = SimSystemClient()
    try:
        service_state = client.get_service(service)
        scenario_id = service_state.get("active_scenario_id")
        if not scenario_id:
            return {"reset_scenario": False, "reason": f"{service} has no active failure scenario"}
        client.reset_scenario(scenario_id)
        return {"reset_scenario": True, "scenario_id": scenario_id}
    finally:
        client.close()


def restart_service(db: Session, params: RestartServiceInput) -> dict:
    outcome = _reset_active_scenario_for_service(params.service)
    return {
        "action": "restart_service",
        "service": params.service,
        "reason": params.reason,
        **outcome,
    }


def rollback_deploy(db: Session, params: RollbackDeployInput) -> dict:
    outcome = _reset_active_scenario_for_service(params.service)
    return {
        "action": "rollback_deploy",
        "service": params.service,
        "target_sha": params.target_sha,
        "reason": params.reason,
        **outcome,
    }


def post_status_update(db: Session, params: PostStatusUpdateInput) -> dict:
    # Nothing in this project's scope to actually post to, there's no
    # status page or chat integration. Recording it here as "posted" is
    # honest: the point being demonstrated is the approval gate, not a
    # fake integration with a system that doesn't exist.
    return {
        "action": "post_status_update",
        "message": params.message,
        "posted": True,
    }
