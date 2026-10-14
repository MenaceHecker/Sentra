import os

# Must be set before anything imports app.config, since get_settings() is
# cached: whoever calls it first wins for the rest of the process. Keeps
# tests from starting the background ingestion loop or touching the real
# dev database at TestClient startup.
os.environ.setdefault("ENABLE_BACKGROUND_JOBS", "false")

from collections.abc import Callable, Generator  # noqa: E402

import app.models  # noqa: E402,F401 -- registers every table on Base.metadata before create_all
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

settings = get_settings()


def _test_database_url() -> str:
    # Tests get their own database so a local test run never touches dev data.
    base_url = settings.database_url.rsplit("/", 1)[0]
    return f"{base_url}/sentra_test"


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    admin_engine = create_engine(settings.database_url)
    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        exists = conn.execute(sa.text("SELECT 1 FROM pg_database WHERE datname = 'sentra_test'")).scalar()
        if not exists:
            conn.execute(sa.text("CREATE DATABASE sentra_test"))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def engine(_test_database: None) -> Generator[sa.Engine, None, None]:
    test_engine = create_engine(_test_database_url())
    with test_engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def db_session(engine: sa.Engine) -> Generator[Session, None, None]:
    # Each test runs inside its own transaction (with savepoints so the
    # endpoint's own db.commit() calls don't escape it), rolled back at
    # the end so tests never see each other's data.
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _get_db_override() -> Generator[Session, None, None]:
        yield db_session

    # The rate limiter's in-memory counters live for the whole test process,
    # not just one test. Resetting here means every test starts with a full
    # allowance regardless of what earlier tests did against the same key
    # (TestClient requests all share one fake client address).
    limiter.reset()
    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def register(client: TestClient) -> Callable[[str, str], dict[str, str]]:
    """Registers a user and returns an Authorization header for them."""

    def _register(email: str, password: str = "password123") -> dict[str, str]:
        response = client.post("/api/auth/register", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _register
