---
trigger: always_on
---

# Agent Instructions: Codebase Query Rules

## Core Rule
Before executing any task, editing files, or answering architecture questions, you **MUST** prioritize querying the codebase knowledge graph using Graphify. Do not perform blind file scans or guess project dependencies.

## Operational Workflow
1. **Initialize Context:** Always run or reference the active Graphify index (`/graphify .`) at the beginning of a codebase task.
2. **Consult the Graph:** Use the local graph map (`graphify-out/GRAPH_REPORT.md`) to trace functions, identify dependencies, and locate relevant files.
3. **Verify Constraints:** Only modify files after confirming their structural relationships via the knowledge graph to prevent breaking upstream or downstream code.
