import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.embeddings import get_embedding_provider
from app.ingestion.pipeline import run_ingestion_cycle
from app.ingestion.sim_client import SimSystemClient
from app.rate_limit import limiter
from app.routers import audit, auth, incidents, runbooks, scenarios
from app.runbooks import ingest_all_runbooks
from app.seed import seed_services

settings = get_settings()
logger = logging.getLogger(__name__)


def _run_ingestion_cycle_safely(client: SimSystemClient) -> None:
    try:
        with SessionLocal() as db:
            run_ingestion_cycle(db, client)
    except Exception:
        # The simulated system might just not be up yet, or be mid-restart.
        # Log it and try again next tick instead of crashing the app.
        logger.warning("ingestion cycle failed, will retry next tick", exc_info=True)


async def _ingestion_loop() -> None:
    client = SimSystemClient()
    try:
        while True:
            await asyncio.to_thread(_run_ingestion_cycle_safely, client)
            await asyncio.sleep(settings.ingestion_interval_seconds)
    finally:
        client.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None

    if settings.enable_background_jobs:
        with SessionLocal() as db:
            seed_services(db)
            ingest_all_runbooks(db, get_embedding_provider())
        task = asyncio.create_task(_ingestion_loop())

    yield

    if task is not None:
        task.cancel()


app = FastAPI(
    title="Sentra API",
    version="0.1.0",
    description="AI incident copilot — evidence-grounded triage with a hard human approval gate.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth.router)
app.include_router(incidents.router)
app.include_router(runbooks.router)
app.include_router(audit.router)
app.include_router(scenarios.router)


@app.get("/health")
def health() -> dict:
    """Liveness check: process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    """Readiness check: confirms the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return {"status": "not_ready"}
