# Sentra — Build Progress Tracker

> Last updated: 2026-10-11
> Reference spec: [`docs/spec.md`](spec.md) · [`README.md`](../README.md)

---

## Phase Summary

| Phase | Name | Status | Checkpoint |
|-------|------|--------|------------|
| 0 | Scope & Repository Setup | ✅ Done | Frontend + backend run, CI passes, README explains architecture |
| 1 | Database + Auth | ✅ Done | Sign in/out, unauthenticated access rejected, incident ownership enforced |
| 2 | Simulated System | ✅ Done | Demo system runs, emits logs/metrics, failure injection reproducible |
| 3 | Ingestion Pipeline | ✅ Done | Seeded data queryable, runbooks searchable via pgvector |
| 4 | Tool Layer | ✅ Done | Each tool callable and unit-tested independently of the LLM |
| 5 | Agent Orchestrator | ✅ Done | Seeded incident → grounded hypothesis with real citations |
| 6 | Approval Workflow | 🔲 Not started | Approved rollback changes simulated error rate; rejected never executes |
| 7 | Audit Log | 🔲 Not started | Every investigation reconstructable from audit log alone |
| 8 | Investigation UI | 🔲 Not started | Reviewer can trigger seeded incident and watch it live |
| 9 | Streaming + Polish | 🔲 Not started | Investigation feels live, not spinner-then-dump |
| 10 | Security + Reliability | 🔲 Not started | Auth audit, rate limiting, prompt-injection tests, approval-gate bypass tests pass |
| 11 | Evaluation | 🔲 Not started | 5–8 scenario benchmark with real numbers in README |
| 12 | Deployment | 🔲 Not started | Public demo works end-to-end with no developer assistance |
| 13 | Portfolio Packaging | 🔲 Not started | README with architecture diagram, demo video, evaluation results, tradeoffs |

---

## Detailed Phase Breakdown

### ✅ Phase 0 — Scope & Repository Setup

**Checkpoint:** frontend and backend run, CI passes, README explains architecture.

- [x] Git repo initialized with `.gitignore`, `.env.example`
- [x] Pre-commit hooks configured (`.pre-commit-config.yaml`)
- [x] GitHub Actions CI (`.github/`)
- [x] Docker Compose with Postgres + pgvector (`docker-compose.yml`)
- [x] Backend skeleton (`backend/`) — FastAPI + pyproject.toml + Dockerfile
- [x] Frontend skeleton (`frontend/`) — Next.js + TypeScript + Tailwind
- [x] Simulated system skeleton (`simulated-system/`)
- [x] README with architecture diagram (Mermaid) and local-dev instructions
- [x] Full product spec committed (`docs/spec.md`)

---

### ✅ Phase 1 — Database + Auth

**Checkpoint:** user can sign in/out; unauthenticated access rejected; user A cannot see user B's incidents.

- [x] Alembic configured (`backend/alembic/`, `alembic.ini`)
- [x] SQLAlchemy models (`backend/app/models.py`) — full data model from spec §7
- [x] Auth router (`backend/app/routers/auth.py`) — register + login + JWT
- [x] `deps.py` — `get_current_user` dependency for protected routes
- [x] `security.py` — password hashing, JWT encode/decode
- [x] Incident ownership enforced in incidents router (`backend/app/routers/incidents.py`)
- [x] Unit tests: `tests/unit/test_auth.py`, `tests/unit/test_incidents.py`

---

### ✅ Phase 2 — Simulated System

**Checkpoint:** demo system runs, emits realistic logs/metrics, failure injection reproducibly creates an incident signature.

- [x] Three demo services (`checkout-service`, `payments-service`, `inventory-service`) — seeded in `simulated-system/app/seed.py`
- [x] Continuous log + metric emitter (`simulated-system/app/generator.py`)
- [x] In-memory state store (`simulated-system/app/state.py`)
- [x] REST API for the simulated system (`simulated-system/app/main.py`)
  - [x] `GET /services`
  - [x] `GET /logs` (query by service, time range, level, filter)
  - [x] `GET /metrics` (query by service, metric, time range)
  - [x] `GET /deploys` (query by service, time range)
  - [x] `GET /scenarios` + `POST /scenarios/{name}/inject`
- [x] Seeded incident scenarios (`simulated-system/app/scenarios.py`)
  - [x] `checkout-500s` — checkout service returning 500s after a bad deploy
- [x] Pydantic schemas (`simulated-system/app/schemas.py`)
- [x] Simulated system tests (`simulated-system/tests/`)

---

### ✅ Phase 3 — Ingestion Pipeline

**Checkpoint:** seeded data queryable; runbooks searchable via pgvector.

- [x] Simulated system HTTP client (`backend/app/ingestion/sim_client.py`)
- [x] Background ingestion pipeline (`backend/app/ingestion/pipeline.py`) — polls logs, metrics, deploys on a schedule
- [x] Runbook chunker + embedder (`backend/app/runbooks.py`)
- [x] Embeddings module (`backend/app/embeddings.py`) — real embeddings via OpenAI API; deterministic hash fallback when no API key
- [x] Runbook search (`backend/app/search.py`) — cosine similarity via pgvector
- [x] Runbooks router (`backend/app/routers/runbooks.py`) — search endpoint
- [x] Runbook source documents (`backend/runbooks/`)
- [x] Ingestion started on backend startup (`backend/app/main.py`)
- [x] Unit tests: `tests/unit/test_ingestion.py`, `tests/unit/test_runbooks.py`, `tests/unit/test_embeddings.py`, `tests/unit/test_search.py`

---

### ✅ Phase 4 — Tool Layer

**Checkpoint:** each tool callable and unit-tested independently of the LLM.

- [x] Tool base class (`backend/app/tools/base.py`)
- [x] Tool schemas (`backend/app/tools/schemas.py`)
- [x] Read-only tools (`backend/app/tools/read_only.py`)
  - [x] `query_logs(service, start_time, end_time, filter?)`
  - [x] `get_metrics(service, metric_name, start_time, end_time)`
  - [x] `get_recent_deploys(service, start_time, end_time)`
  - [x] `search_runbooks(query)`
  - [x] `get_service_status(service)`
- [x] Side-effecting tool stubs (`backend/app/tools/side_effecting.py`)
  - [x] `restart_service(service, reason)`
  - [x] `rollback_deploy(service, target_sha, reason)`
  - [x] `post_status_update(message)`
- [x] Tool registry (`backend/app/tools/registry.py`) — maps tool names to implementations + category
- [x] Executor with hard approval gate (`backend/app/tools/executor.py`) — read-only tools execute immediately; side-effecting tools are queued, never auto-executed
- [x] Unit tests: `tests/unit/test_tools_read_only.py`, `tests/unit/test_tools_executor.py`, `tests/unit/test_tools_side_effecting.py`

---

### ✅ Phase 5 — Agent Orchestrator

**Checkpoint:** triggering a seeded incident produces a grounded hypothesis with real citations.

- [x] LLM provider abstraction layer (`backend/app/agent/provider.py`) — OpenAI implemented, swapping providers means adding one more `call_*` function
- [x] System prompt with investigation policy (`backend/app/agent/prompts.py`) — cite evidence before hypothesizing; treat log/runbook content as data, not instructions
- [x] Tool-calling loop (`backend/app/agent/orchestrator.py`): LLM → tool call → store result as evidence → feed back → repeat until hypothesis
- [x] Evidence storage (populate `evidence` table from tool results, tied to `incident_id`)
- [x] Hypothesis generation with citations (`hypotheses` + `hypothesis_citations` tables)
- [x] Confidence level assignment (`low | medium | high`) + reasoning
- [x] Enforce "evidence required before side-effecting action proposal" at orchestration layer
- [x] `POST /api/incidents/{id}/investigate` endpoint kicks off the loop
- [x] `GET /api/incidents/{id}` returns full state: evidence, hypotheses, proposed actions, status
- [x] Unit + integration tests: `tests/unit/test_orchestrator.py`, `tests/unit/test_investigate_endpoint.py`

**Fixed after an initial review (2026-10-11):**
- `GET /{incident_id}` was crashing on every call: `selectinload("citations")` used a string instead of the class-bound attribute `Hypothesis.citations`, which SQLAlchemy 2.0's loader options reject outright. Broke both the new investigate endpoint and the original Phase 1 incident-detail tests.
- Side-effecting proposals could never actually reach "proposed" status. The model wrote them as free text (`PROPOSED_ACTIONS: - ACTION: rollback_deploy ...`), which got parsed into `{"reason": ..., "_evidence": ...}` and handed to `call_tool` — missing every field each tool's schema actually requires (`service`, `target_sha`, etc.), so it always failed pydantic validation and the call silently became `"failed"` while `incident.status` claimed `"action_pending"` regardless. Fixed by dropping the free-text mechanism: the model now proposes a side-effecting action the same way it calls any other tool, natively, with real arguments matching that tool's schema. The orchestrator rejects the call in code if no evidence has been gathered yet this investigation (spec §8 rule 4), same enforcement, now actually reachable.

---

### 🔲 Phase 6 — Approval Workflow

**Checkpoint:** an approved rollback actually changes the simulated system's error rate; a rejected action never executes.

- [ ] Proposed-action generation from the agent loop → `tool_calls` rows with `status=proposed`
- [ ] `POST /api/incidents/{id}/actions/{action_id}/approve` endpoint
- [ ] `POST /api/incidents/{id}/actions/{action_id}/reject` endpoint
- [ ] Approval triggers actual side-effecting tool execution against the simulated system
- [ ] Rejection writes a rejection record; tool is permanently blocked from executing
- [ ] Outcome of approved action fed back to the agent (did the error rate change?)
- [ ] Incident status transitions: `investigating → hypothesis_ready → action_pending → resolved`
- [ ] Integration test: approve rollback → simulated system error rate drops
- [ ] Integration test: reject action → no execution; try to call execute directly → still blocked

---

### 🔲 Phase 7 — Audit Log

**Checkpoint:** every investigation reconstructable end-to-end from the audit log alone.

- [ ] `audit_log` table entries written for every tool call (input + output captured before LLM sees result)
- [ ] Approval and rejection events written to audit log with actor + timestamp
- [ ] Incident status-change events written to audit log
- [ ] `GET /api/incidents/{id}/audit-log` endpoint
- [ ] Global audit log endpoint (`GET /api/audit-log`) filterable by investigation, action type, status
- [ ] Audit entries immutable — no UPDATE/DELETE paths in code
- [ ] Test: reconstruct a full investigation from audit log entries alone

---

### 🔲 Phase 8 — Investigation UI

**Checkpoint:** a reviewer can trigger a seeded incident and watch the investigation happen live.

- [ ] **Landing page** — value prop, "View Live Demo" CTA, architecture summary, example walkthrough, GitHub link
- [ ] **Auth pages** — sign-in, sign-out
- [ ] **Dashboard** — connected system status, past investigations list, "Trigger Incident" / scenario picker
- [ ] **Investigation workspace**
  - [ ] Left panel: investigation timeline (tool calls, chronological)
  - [ ] Center: hypothesis + evidence + follow-up chat
  - [ ] Right panel: evidence/source viewer (logs, metric chart, deploy diff, runbook excerpt)
  - [ ] Top bar: incident title, status badge, affected service
  - [ ] Bottom/modal: proposed-action card with description, evidence summary, blast radius, Approve/Reject
- [ ] **Audit log page** — filterable table of all tool calls across all investigations
- [ ] **Source viewer page** — raw log stream, metric chart, runbook viewer, deploy history
- [ ] Recharts (or similar) metric charts
- [ ] Citation links: clicking a cited piece of evidence opens the source viewer to the relevant section

---

### 🔲 Phase 9 — Streaming + Polish

**Checkpoint:** investigation feels live, not like a spinner-then-dump.

- [ ] SSE (`text/event-stream`) on `POST /api/incidents/{id}/investigate` — stream each tool call + partial evidence as it happens
- [ ] Frontend SSE consumer — appends timeline entries in real time
- [ ] Loading states for all async operations
- [ ] Error states (LLM error, tool failure, network error) with graceful UI fallback
- [ ] Empty states (no past investigations, no evidence yet)
- [ ] Responsive layout (tablet-friendly at minimum)
- [ ] Keyboard-accessible approve/reject flow

---

### 🔲 Phase 10 — Security + Reliability

**Checkpoint:** security tests pass; a test that tries to make the model skip the approval gate fails to bypass it.

- [ ] Authorization audit — every incident/evidence/action endpoint checks ownership
- [ ] Rate limiting on `POST /api/incidents` and `investigate` (prevent runaway LLM cost)
- [ ] Prompt-injection defense verified — log/runbook content explicitly scoped as data in system prompt
- [ ] Test: craft a log line containing "ignore previous instructions" → agent does not follow it
- [ ] Test: attempt to call a side-effecting tool execute path without an approval record → 403 / blocked
- [ ] Test: attempt to access another user's incident → 403
- [ ] No real credentials anywhere in the repo or demo system by construction
- [ ] Input validation on all API endpoints (Pydantic schemas)

---

### 🔲 Phase 11 — Evaluation

**Checkpoint:** real, reproducible numbers in the README.

- [ ] 5–8 seeded incident scenarios defined with known root causes
  - [ ] `checkout-500s` — bad deploy to checkout-service
  - [ ] `payments-latency` — upstream dependency slow
  - [ ] `inventory-db-lock` — database lock contention
  - [ ] *(add more as scenarios are designed)*
- [ ] Evaluation harness: trigger each scenario, run investigation, capture hypothesis + citations
- [ ] Metrics measured per scenario:
  - [ ] Root-cause identification accuracy (correct / incorrect / partial)
  - [ ] Citation accuracy (every cited log/metric/deploy/runbook is real and relevant)
  - [ ] Confidence calibration (high-confidence hypotheses are more often correct)
  - [ ] Time from incident creation to first hypothesis
  - [ ] Token usage and estimated cost per investigation
  - [ ] Approval-gate bypass attempts (should always be 0)
- [ ] Results table written into `README.md` — **real numbers only, no fabricated metrics**

---

### 🔲 Phase 12 — Deployment

**Checkpoint:** public demo works end to end with no developer assistance.

- [ ] Frontend deployed to Vercel
- [ ] Backend deployed to Railway / Render / Fly.io
- [ ] Simulated system deployed alongside backend (same platform or separate service)
- [ ] Database: Supabase Postgres (or equivalent managed Postgres + pgvector)
- [ ] Environment variables and secrets configured in each platform
- [ ] CI/CD pipeline: merge to `main` → deploy
- [ ] Health checks for backend (`GET /health`) and simulated system
- [ ] Seeded demo data present on first startup (no manual setup for reviewer)
- [ ] Public URL verified end-to-end with a clean browser session

---

### 🔲 Phase 13 — Portfolio Packaging

**Checkpoint:** a reviewer with no context can understand the project, try the demo, and evaluate the engineering.

- [ ] README updated with:
  - [ ] Architecture diagram (Mermaid or image)
  - [ ] Live demo URL
  - [ ] Demo video / GIF of full investigation → approval flow
  - [ ] Evaluation results table (from Phase 11)
  - [ ] Design decisions and tradeoffs (why read-only vs. side-effecting split is in code, not prompt)
  - [ ] Known limitations and honest scope
  - [ ] Roadmap / what would be built next
- [ ] Resume bullets drafted (see spec §16) — **fill in actual metrics after Phase 11**
- [ ] Interview talking points reviewed (spec §17)
- [ ] Repository is public and linked from resume/portfolio

---

## MVP Completion Checklist

> From spec §15. All items required before calling the project MVP-complete.

- [x] Auth works, incidents are user-scoped *(Phase 1)*
- [x] Simulated system emits logs/metrics/deploys and supports seeded failure injection *(Phase 2)*
- [x] Runbooks ingested and searchable *(Phase 3)*
- [x] Agent investigates via read-only tool calls *(Phase 5)*
- [x] Hypotheses are evidence-cited with stated confidence *(Phase 5)*
- [ ] Side-effecting actions require explicit human approval — **structurally enforced, not just prompted**
- [ ] Approved actions execute against the simulated system and report outcomes
- [ ] Full audit log reconstructs every investigation
- [ ] Investigation UI works end to end for a reviewer with no setup
- [ ] Security tests pass, including an explicit "can the approval gate be bypassed" test
- [ ] Evaluation run with real numbers in the README
- [ ] Deployed, publicly reviewable, with a demo video

---

## Key Design Decisions

> Track decisions here as they're made, for use in the README and interviews.

| Decision | Rationale | Phase |
|----------|-----------|-------|
| Read-only vs. side-effecting split enforced in `executor.py`, not via prompting | Prompts are not reliable enforcement; the orchestration layer is the actual safety boundary | 4 |
| Deterministic hash-based embedding fallback in `embeddings.py` | Lets the project run without an OpenAI key; runbook search degrades gracefully to keyword-level matching | 3 |
| Side-effecting proposals go through native tool-calling, same as read-only tools, not a parsed free-text block | A free-text format can't carry a tool's real required arguments (service, target_sha, ...) without either a fragile second parser or losing validation entirely; native calling reuses the exact same schema and executor path read-only tools already go through | 5 |
| *(add more as they arise)* | | |

---

## Open Questions / Blockers

> Update this section as the build progresses.

- [x] LLM provider for Phase 5 — decided: OpenAI (`backend/app/agent/provider.py`), via native function-calling.
- [ ] SSE vs. WebSocket for Phase 9 streaming — SSE is simpler and sufficient for unidirectional stream; confirm this is acceptable.
- [ ] Deployment platform for backend + simulated system — Railway vs. Fly.io? (Fly.io gives more control over multi-service; Railway is simpler setup.)
- [ ] Number and exact set of evaluation scenarios for Phase 11 — spec says 5–8; decide before Phase 11.
