# Sentra

**AI incident copilot.**

Connect your system's logs, metrics, and runbooks. When something breaks,
Sentra investigates via autonomous read-only tool calls, produces an
evidence-cited root-cause hypothesis, and proposes next actions, but no
side-effecting action ever executes without explicit human approval.

> Status: early build — see [Roadmap](#roadmap) for what's done vs. planned.

**Live demo:** [frontend-menaceheckers-projects.vercel.app](https://frontend-menaceheckers-projects.vercel.app) — sign up, pick a seeded scenario, and watch a real investigation run against the real Gemini API. No setup needed.

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
Frontend runs at `http://localhost:3000`. Sign up, then on the dashboard
pick a seeded scenario and click "Trigger incident", it injects the
failure into the simulated system and opens an investigation for it.
Click Investigate, then approve or reject whatever it proposes.

### 5. Pre-commit hooks
```bash
pip install pre-commit
pre-commit install
```

## Evaluation

6 seeded incident scenarios (2 per service, a deploy-caused failure and a
non-deploy one, so the model has to actually distinguish root causes rather
than pattern-match "blame the last deploy"), run twice each: 12 real
investigations against the real Gemini API (`gemini-3.5-flash-lite`), driven
over HTTP exactly the way a reviewer clicking through the UI would, via
[`backend/evaluation/run_eval.py`](backend/evaluation/run_eval.py). Raw
per-run output (every hypothesis, citation, token count) is committed at
[`backend/evaluation/results.json`](backend/evaluation/results.json). These
are the only numbers below; none are estimated or rounded up from a smaller
run.

| Scenario | Root cause | Runs | Verdict | Confidence |
|---|---|---|---|---|
| `checkout-500s` | Deploy broke request schema (missing `shipping_method`) | 2 | 2/2 correct | high, high |
| `checkout-slow-carrier` | Slow external dependency, not a deploy | 2 | 2/2 correct | high, high |
| `payments-timeout` | Deploy shrank the provider connection pool | 2 | 2/2 correct | high, high |
| `payments-bad-credentials` | Stale API credential, not a deploy | 2 | 2/2 correct | high, high |
| `inventory-oom` | Deploy introduced an unbounded cache (memory leak) | 2 | 2/2 correct | high, high |
| `inventory-db-lock` | External lock contention, not a deploy | 2 | 2/2 correct* | high, high |

\* see **Known limitation** below — one of the two `inventory-db-lock` runs
got the right *mechanism* but cited the wrong *cause*.

**Root-cause accuracy:** 12/12 (100%) graded "correct" by a simple, fixed,
disclosed rubric (`RUBRIC` in the harness script): a hypothesis counts as
correct if its summary+reasoning text contains a scenario-specific keyword
or phrase naming the actual root cause, decided before any run happened, not
judged after the fact. This is a small sample against a rubric that only
checks whether the right *keywords* showed up, not a claim of rigorous NLP
grading — see Known limitation below for a case this rubric doesn't catch.

**Citation accuracy:** 12/12 runs (100%) had every cited evidence ID resolve
to a real `Evidence` row backed by a real executed tool call from that same
investigation, checked structurally, not sampled.

**Confidence calibration:** not meaningfully measurable from this run — all
12 hypotheses came back "high" confidence and all 12 were graded correct, so
there's no spread of confidence-vs-correctness to calibrate against. A
larger, more adversarial scenario set (ambiguous evidence, conflicting
signals) would be needed to actually test this.

**Time to first hypothesis:** avg 24.1s, min 9.0s, max 52.4s (wall clock
from `POST /investigate` to the hypothesis landing, real network + real LLM
latency included).

**Token usage & cost:** avg 26,075 prompt + 392 completion tokens per
investigation (312,895 + 4,703 total across all 12 runs). Actual cost was
$0 — this ran on Gemini's free tier. At `gemini-3.5-flash-lite`'s published
paid-tier rate ([$0.30/1M input, $2.50/1M output tokens, per third-party
pricing trackers citing Google's rate sheet as of August 2026](https://anotherwrapper.com/tools/llm-pricing/gemini-3.5-flash-lite),
not independently confirmed against Google's own page), that works out to
roughly **$0.009 per investigation** (~$0.11 for all 12 runs).

**Approval-gate bypass attempts:** 0 across all 12 runs. Every proposed
side-effecting tool call stayed in `"proposed"` status; none reached
`"executed"` without a human approval record, checked structurally against
every tool call in every run, not just spot-checked.

**Known limitation, found by this evaluation, not hidden from it:** on
`inventory-db-lock` run #2, the hypothesis cited an unrelated deploy
(`"Cache stock-reservation lookups in memory"`, actually from an earlier
`inventory-oom` run in the same harness session) as a contributing cause,
even though `inventory-db-lock` has no deploy of its own by design, it's
meant to test whether the model avoids blaming a deploy when there isn't
one. Root cause of the mix-up: the harness called a scenario-reset endpoint
that didn't exist yet (silently 404ing), so deploy history kept
accumulating across back-to-back scenario injections in the same long-running
simulated-system process instead of being cleared between them. The
evaluation run is what surfaced this, which is exactly what an evaluation is
for: `POST /api/scenarios/{id}/reset` was added to the backend as a result
(previously only used internally by the approval-gated remediation tools,
never exposed), the harness now calls a real endpoint, and this is
documented rather than quietly re-run until it looked clean. The original
12-run dataset above is kept as-is, unedited.

## Roadmap

- [x] Phase 0 — Scope & repository setup
- [x] Phase 1 — Database + auth
- [x] Phase 2 — Simulated system
- [x] Phase 3 — Ingestion pipeline
- [x] Phase 4 — Tool layer
- [x] Phase 5 — Agent orchestrator
- [x] Phase 6 — Approval workflow
- [x] Phase 7 — Audit log
- [x] Phase 8 — Investigation UI
- [x] Phase 9 — Streaming + polish
- [x] Phase 10 — Security + reliability
- [x] Phase 11 — Evaluation
- [x] Phase 12 — Deployment
- [ ] Phase 13 — Portfolio packaging

## License

MIT