import pytest
from app.tools import side_effecting
from app.tools.schemas import PostStatusUpdateInput, RestartServiceInput, RollbackDeployInput
from app.tools.side_effecting import post_status_update, restart_service, rollback_deploy
from sqlalchemy.orm import Session

from tests.fakes import FakeSimSystemClient


@pytest.fixture
def fake_sim_client(monkeypatch: pytest.MonkeyPatch) -> FakeSimSystemClient:
    fake = FakeSimSystemClient(
        services_by_name={
            "checkout-service": {"name": "checkout-service", "active_scenario_id": "checkout-500s"},
            "payments-service": {"name": "payments-service", "active_scenario_id": None},
        }
    )
    monkeypatch.setattr(side_effecting, "SimSystemClient", lambda base_url=None: fake)
    return fake


def test_restart_service_resets_the_active_scenario(db_session: Session, fake_sim_client: FakeSimSystemClient) -> None:
    result = restart_service(db_session, RestartServiceInput(service="checkout-service", reason="error spike"))

    assert result["action"] == "restart_service"
    assert result["reset_scenario"] is True
    assert result["scenario_id"] == "checkout-500s"
    assert fake_sim_client.reset_scenario_calls == ["checkout-500s"]


def test_rollback_deploy_resets_the_active_scenario(db_session: Session, fake_sim_client: FakeSimSystemClient) -> None:
    result = rollback_deploy(
        db_session,
        RollbackDeployInput(service="checkout-service", target_sha="abc123", reason="bad deploy"),
    )

    assert result["action"] == "rollback_deploy"
    assert result["target_sha"] == "abc123"
    assert result["reset_scenario"] is True
    assert fake_sim_client.reset_scenario_calls == ["checkout-500s"]


def test_restart_service_is_honest_when_nothing_is_active(
    db_session: Session, fake_sim_client: FakeSimSystemClient
) -> None:
    result = restart_service(db_session, RestartServiceInput(service="payments-service", reason="just in case"))

    assert result["reset_scenario"] is False
    assert fake_sim_client.reset_scenario_calls == []


def test_post_status_update_does_not_touch_the_simulated_system(db_session: Session) -> None:
    result = post_status_update(db_session, PostStatusUpdateInput(message="investigating checkout errors"))
    assert result == {
        "action": "post_status_update",
        "message": "investigating checkout errors",
        "posted": True,
    }
