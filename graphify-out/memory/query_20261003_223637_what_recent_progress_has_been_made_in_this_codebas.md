---
type: "query"
date: "2026-10-03T22:36:37.839563+00:00"
question: "What recent progress has been made in this codebase? What is the agent investigation loop, incidents API, and current architecture?"
contributor: "graphify"
source_nodes: ["Architecture", "call_tool", "Hypothesis", "Incident", "Evidence"]
---

# Q: What recent progress has been made in this codebase? What is the agent investigation loop, incidents API, and current architecture?

## Answer

The graph is stale relative to uncommitted Phase 5 work. As of the last extracted graph (HEAD 2777cf4, report also notes 21c688e1), Sentra's committed core is ingestion (logs/metrics/deploys via SimSystemClientProtocol), the tool executor call_tool() as the spec-8 approval gate, and models Incident/ToolCall/Evidence/Hypothesis/HypothesisCitation/AuditLog. The uncommitted agent orchestrator, provider, prompts, and POST /investigate are not in the graph yet.

## Source Nodes

- Architecture
- call_tool
- Hypothesis
- Incident
- Evidence