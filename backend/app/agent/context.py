"""Evidence → LLM context formatting (spec §9).

Each piece of evidence is formatted into a clearly-labelled block so the
model can cite it precisely.  The TYPE / SERVICE / TIME header makes every
block machine-parseable for future use.

SECURITY: All content is wrapped inside DATA: blocks and the system prompt
instructs the model to treat anything inside them as untrusted data.  A
log line that says "ignore previous instructions" is just a string here.
"""

from __future__ import annotations

import json
from typing import Any


def format_log_evidence(tool_output: dict[str, Any]) -> str:
    """Format query_logs output as an evidence block."""
    service = tool_output.get("service", "unknown")
    logs = tool_output.get("logs", [])
    lines = [f"TYPE: log\nSERVICE: {service}\nCOUNT: {len(logs)}\nDATA:"]
    for entry in logs:
        ts = entry.get("timestamp", "")
        level = entry.get("level", "")
        msg = entry.get("message", "")
        tid = entry.get("trace_id") or ""
        trace_part = f" trace_id={tid}" if tid else ""
        lines.append(f"  [{ts}] {level}{trace_part}: {msg}")
    return "\n".join(lines)


def format_metric_evidence(tool_output: dict[str, Any]) -> str:
    """Format get_metrics output as an evidence block."""
    service = tool_output.get("service", "unknown")
    metric = tool_output.get("metric_name", "unknown")
    points = tool_output.get("points", [])
    values = [p.get("value", 0) for p in points]
    min_v = min(values) if values else None
    max_v = max(values) if values else None
    avg_v = sum(values) / len(values) if values else None

    lines = [
        f"TYPE: metric",
        f"SERVICE: {service}",
        f"METRIC: {metric}",
        f"WINDOW: {points[0]['timestamp'] if points else 'N/A'} — {points[-1]['timestamp'] if points else 'N/A'}",
        f"MIN: {min_v:.4f}  MAX: {max_v:.4f}  AVG: {avg_v:.4f}" if values else "NO DATA",
        "DATA:",
    ]
    for p in points:
        lines.append(f"  {p.get('timestamp', '')}: {p.get('value', 0):.4f}")
    return "\n".join(lines)


def format_deploy_evidence(tool_output: dict[str, Any]) -> str:
    """Format get_recent_deploys output as an evidence block."""
    service = tool_output.get("service", "unknown")
    deploys = tool_output.get("deploys", [])
    lines = [f"TYPE: deploy\nSERVICE: {service}\nCOUNT: {len(deploys)}\nDATA:"]
    for d in deploys:
        sha = d.get("sha", "")[:8]
        ts = d.get("deployed_at", "")
        msg = d.get("message", "")
        by = d.get("deployed_by", "")
        lines.append(f"  sha={sha} at={ts} by={by}: {msg}")
    return "\n".join(lines)


def format_runbook_evidence(tool_output: dict[str, Any]) -> str:
    """Format search_runbooks output as an evidence block."""
    query = tool_output.get("query", "")
    results = tool_output.get("results", [])
    lines = [f"TYPE: runbook\nQUERY: {query}\nRESULTS: {len(results)}\nDATA:"]
    for r in results:
        title = r.get("document_title", "")
        start = r.get("start_line", 0)
        end = r.get("end_line", 0)
        content = r.get("content", "")
        lines.append(f"\n  DOCUMENT: {title}  LINES: {start}-{end}")
        lines.append(f"  {content}")
    return "\n".join(lines)


def format_status_evidence(tool_output: dict[str, Any]) -> str:
    """Format get_service_status output as an evidence block."""
    service = tool_output.get("service", "unknown")
    status = tool_output.get("status", "unknown")
    rate = tool_output.get("latest_error_rate")
    as_of = tool_output.get("as_of", "")
    rate_str = f"{rate:.4f}" if rate is not None else "N/A"
    return (
        f"TYPE: service_status\n"
        f"SERVICE: {service}\n"
        f"STATUS: {status}\n"
        f"LATEST_ERROR_RATE: {rate_str}\n"
        f"AS_OF: {as_of}"
    )


FORMATTERS = {
    "query_logs": format_log_evidence,
    "get_metrics": format_metric_evidence,
    "get_recent_deploys": format_deploy_evidence,
    "search_runbooks": format_runbook_evidence,
    "get_service_status": format_status_evidence,
}


def format_tool_result_for_context(tool_name: str, tool_output: dict[str, Any]) -> str:
    """Return a formatted evidence block for a given tool result.

    Falls back to a JSON dump for any tool not in FORMATTERS (e.g. during
    testing or if new tools are added without a formatter).
    """
    formatter = FORMATTERS.get(tool_name)
    if formatter is None:
        return f"TYPE: raw\nTOOL: {tool_name}\nDATA:\n{json.dumps(tool_output, indent=2)}"
    return formatter(tool_output)
