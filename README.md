# Sentra

**AI incident copilot.**

Connect your system's logs, metrics, and runbooks. When something breaks,
Sentra investigates via autonomous read-only tool calls, produces an
evidence-cited root-cause hypothesis, and proposes next actions but no
side-effecting action ever executes without explicit human approval.

> Status: early build — see [Roadmap](#roadmap) for what's done vs. planned.

## Architecture

```mermaid
flowchart LR
	Next[Next.js React TypeScript] -->|HTTPS| API[FastAPI API and Agent Orchestrator]
	API --> PostgreSQL[(PostgreSQL: incidents, tool calls, approvals, audit log)]
	API --> Simulated[Simulated System: logs, metrics, deploys API]
	PostgreSQL --> Vectors[(pgvector: runbook chunks)]
```

The core design constraint: the distinction between read-only tools (agent
calls autonomously) and side-effecting tools (agent may only *propose*,
human must approve) is enforced at the orchestration layer in code — not by
prompting the model to behave. See `docs/spec.md` for the full design.

## Tech stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy
- **Database:** PostgreSQL + pgvector
- **LLM:** hosted provider with native tool-calling, behind an abstraction layer

## Local development

### Prerequisites
- Docker (for Postgres + pgvector)
- Python 3.12+
- Node 20+

### 1. Database
```bash
docker compose up -d
```

### 2. Simulated system
```bash
cd simulated-system
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 9000
```
Runs at `http://localhost:9000`. This is the fake system Sentra investigates:
three demo services (`checkout-service`, `payments-service`, `inventory-service`)
that continuously emit logs, metrics, and deploy history on their own. Check
`GET /services` to see them, and `POST /scenarios/checkout-500s/inject` to
trigger a reproducible incident (`GET /scenarios` lists what's available).
Start this before the backend, since the backend ingests from it.

### 3. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env   # fill in secrets
alembic upgrade head          # creates the schema
uvicorn app.main:app --reload
```
Backend runs at `http://localhost:8000`. Check `GET /health`. On startup it
seeds the three services, ingests the runbooks in `backend/runbooks/` into
pgvector, and starts pulling logs, metrics, and deploys from the simulated
system every few seconds. `OPENAI_API_KEY` is optional for runbook search:
without one, embeddings fall back to a deterministic hash-based embedding
(`app/embeddings.py`), so search still works with no setup, just with
keyword-level rather than semantic matching. Actually running
`POST /api/incidents/{id}/investigate`, though, needs a real key: set
`LLM_PROVIDER` to `openai` or `gemini` and fill in the matching `*_API_KEY`,
there's no fallback for that call. Gemini has a genuinely free tier (Google
AI Studio, no card needed); stick to a `*-flash-lite` model if you're on it,
flagship models get a tiny daily quota and model names churn fast enough
that it's worth checking `client.models.list()` if a model 404s on you.

### 4. Frontend
```bash
cd frontend
npm install
cp ../.env.example .env.local   # keep only NEXT_PUBLIC_API_URL
npm run dev
```
Frontend runs at `http://localhost:3000`.

### 5. Pre-commit hooks
```bash
pip install pre-commit
pre-commit install
```

## Roadmap

- [x] Phase 0 — Scope & repository setup
- [x] Phase 1 — Database + auth
- [x] Phase 2 — Simulated system
- [x] Phase 3 — Ingestion pipeline
- [x] Phase 4 — Tool layer
- [x] Phase 5 — Agent orchestrator
- [x] Phase 6 — Approval workflow
- [ ] Phase 7 — Audit log
- [ ] Phase 8 — Investigation UI
- [ ] Phase 9 — Streaming + polish
- [ ] Phase 10 — Security + reliability
- [ ] Phase 11 — Evaluation
- [ ] Phase 12 — Deployment
- [ ] Phase 13 — Portfolio packaging

## License

MIT