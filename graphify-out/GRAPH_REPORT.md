# Graph Report - Sentra  (2026-10-03)

## Corpus Check
- 84 files · ~17,883 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 524 nodes · 906 edges · 44 communities (36 shown, 8 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 118 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `21c688e1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]

## God Nodes (most connected - your core abstractions)
1. `SENTRA` - 20 edges
2. `FakeEmbeddingProvider` - 19 edges
3. `seed_services()` - 17 edges
4. `compilerOptions` - 16 edges
5. `Base` - 15 edges
6. `Detailed Phase Breakdown` - 15 edges
7. `call_tool()` - 14 edges
8. `ingest_runbook_file()` - 12 edges
9. `ingest_all_runbooks()` - 12 edges
10. `FakeSimSystemClient` - 12 edges

## Surprising Connections (you probably didn't know these)
- `AuditLog` --uses--> `Base`  [INFERRED]
  backend/app/models.py → backend/app/db.py
- `Deploy` --uses--> `Base`  [INFERRED]
  backend/app/models.py → backend/app/db.py
- `Evidence` --uses--> `Base`  [INFERRED]
  backend/app/models.py → backend/app/db.py
- `Hypothesis` --uses--> `Base`  [INFERRED]
  backend/app/models.py → backend/app/db.py
- `HypothesisCitation` --uses--> `Base`  [INFERRED]
  backend/app/models.py → backend/app/db.py

## Import Cycles
- None detected.

## Communities (44 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (39): EmbeddingProvider, FakeEmbeddingProvider, get_embedding_provider(), OpenAIEmbeddingProvider, Deterministic, dependency-free embedding used whenever no real     provider is c, chunk_markdown(), ingest_all_runbooks(), ingest_runbook_file() (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (52): IncidentCreate, IncidentOut, RunbookDocumentOut, RunbookSearchResultOut, UserCreate, UserLogin, UserOut, BaseModel (+44 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (44): Run migrations in 'offline' mode.      This configures the context with just a U, Run migrations in 'online' mode.      In this scenario we need to create an Engi, run_migrations_offline(), run_migrations_online(), Base, get_db(), Session, get_current_user() (+36 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (32): Detailed Phase Breakdown, Key Design Decisions, MVP Completion Checklist, Open Questions / Blockers, ✅ Phase 0 — Scope & Repository Setup, 🔲 Phase 10 — Security + Reliability, 🔲 Phase 11 — Evaluation, 🔲 Phase 12 — Deployment (+24 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (34): 10. INVESTIGATION / CHAT API, 11. SECURITY REQUIREMENTS, 12. OBSERVABILITY, 13. TESTING & EVALUATION, 14. DEVELOPMENT PHASES, 15. MVP DEFINITION, 16. PORTFOLIO POSITIONING, 17. INTERVIEW TALKING POINTS (+26 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (25): ingest_deploys(), ingest_logs(), ingest_metrics(), _latest_timestamp(), datetime, Session, UUID, run_ingestion_cycle() (+17 more)

### Community 6 - "Community 6"
Cohesion: 0.20
Nodes (23): get_metrics(), get_recent_deploys(), _get_service(), get_service_status(), Session, query_logs(), search_runbooks(), GetMetricsInput (+15 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (23): dependencies, next, react, react-dom, devDependencies, autoprefixer, eslint, eslint-config-next (+15 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (20): Session, Idempotent, safe to call on every startup., seed_services(), call_tool(), Any, Session, UUID, The orchestration-layer gate from spec Section 8. This function, not     the mod (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.43
Nodes (7): TestClient, test_inject_marks_service_degraded_and_creates_a_deploy(), test_inject_unknown_scenario_returns_404(), test_injecting_one_scenario_does_not_affect_other_services(), test_list_scenarios_returns_all_inactive_at_baseline(), test_reset_returns_service_to_healthy(), test_reset_unknown_scenario_returns_404()

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.25
Nodes (4): Any, datetime, Thin sync HTTP client over the simulated system's API. Kept     deliberately sim, SimSystemClient

### Community 12 - "Community 12"
Cohesion: 0.27
Nodes (11): PostStatusUpdateInput, RestartServiceInput, RollbackDeployInput, post_status_update(), Session, restart_service(), rollback_deploy(), Session (+3 more)

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (10): TestClient, test_login_with_correct_credentials_succeeds(), test_login_with_unknown_email_rejected(), test_login_with_wrong_password_rejected(), test_me_rejects_garbage_token(), test_me_requires_authentication(), test_me_returns_current_user(), test_register_rejects_duplicate_email() (+2 more)

### Community 14 - "Community 14"
Cohesion: 0.08
Nodes (23): get_settings(), Settings, health(), _ingestion_loop(), lifespan(), FastAPI, Liveness check: process is up., Readiness check: confirms the database is reachable. (+15 more)

### Community 15 - "Community 15"
Cohesion: 0.22
Nodes (8): Checkout Service, Dependencies, Elevated latency without elevated errors, Escalation, Known issues, Missing shipping_method field causes 500s, Normal operating range, Overview

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (8): Dependencies, Escalation, How this differs from a normal blip, Inventory Service, Known issues, Normal operating range, Overview, Worker restarts from a stock-reservation cache leak

### Community 17 - "Community 17"
Cohesion: 0.22
Nodes (8): Dependencies, Distinguishing "we caused it" from "they caused it", Escalation, Known issues, Normal operating range, Overview, Payments Service, Provider timeouts after a connection pool change

### Community 18 - "Community 18"
Cohesion: 0.43
Nodes (7): TestClient, test_create_incident_requires_authentication(), test_fetching_nonexistent_incident_returns_404(), test_list_incidents_is_scoped_to_the_current_user(), test_list_incidents_requires_authentication(), test_user_can_create_and_fetch_own_incident(), test_user_cannot_fetch_another_users_incident()

### Community 19 - "Community 19"
Cohesion: 0.43
Nodes (7): TestClient, test_deploy_history_is_seeded_at_startup(), test_get_unknown_service_returns_404(), test_list_services_returns_all_three_healthy(), test_logs_are_generated_at_startup(), test_logs_for_unknown_service_returns_404(), test_metrics_are_generated_at_startup()

## Knowledge Gaps
- **123 isolated node(s):** `Tool`, `extends`, `metadata`, `nextConfig`, `name` (+118 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `seed_services()` connect `Community 8` to `Community 5`, `Community 14`, `Community 6`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `FakeEmbeddingProvider` connect `Community 0` to `Community 6`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `FakeEmbeddingProvider` (e.g. with `test_embed_is_deterministic()` and `test_embed_is_normalized()`) actually correct?**
  _`FakeEmbeddingProvider` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `seed_services()` (e.g. with `lifespan()` and `Service`) actually correct?**
  _`seed_services()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Run migrations in 'offline' mode.      This configures the context with just a U`, `Run migrations in 'online' mode.      In this scenario we need to create an Engi`, `Deterministic, dependency-free embedding used whenever no real     provider is c` to the rest of the system?**
  _140 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08244897959183674 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.0574400723654455 - nodes in this community are weakly interconnected._