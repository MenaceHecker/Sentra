"""Agent orchestrator — the core of Sentra.

This module runs the LLM tool-calling loop for a single investigation:

  1. Build initial messages from the incident description.
  2. Call the LLM.
  3. For each tool call the model requests:
       a. Route through call_tool() (the approval-gate layer from Phase 4).
       b. Store the tool call and its output as Evidence in the DB.
       c. Append the tool result to the message history.
  4. Repeat until the model returns a final response (no tool calls).
  5. Parse the structured HYPOTHESIS / CONFIDENCE / PROPOSED_ACTIONS block.
  6. Write the Hypothesis + HypothesisCitations to the DB.
  7. Write an AuditLog entry for the full investigation run.
  8. Yield InvestigationEvent objects for SSE streaming (Phase 9 will use them).

Key design constraints from spec §8:
  - The distinction between read-only and side-effecting tools is enforced
    in call_tool(), never here or in the prompt.
  - Every tool call (input + output) is persisted before the model sees
    the result.
  - A side-effecting proposal with no cited evidence is rejected here
    before it reaches the UI.
  - Max iterations cap prevents infinite loops / runaway cost.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generator

from sqlalchemy.orm import Session

from app.agent.context import format_tool_result_for_context
from app.agent.prompts import build_initial_messages, build_tool_schemas
from app.agent.provider import ProviderResponse, call_llm
from app.models import AuditLog, Evidence, Hypothesis, HypothesisCitation, Incident, ToolCall

logger = logging.getLogger(__name__)

# Safety cap: the model will never make more than this many tool calls in a
# single investigation.  Prevents runaway loops and cost explosions.
MAX_TOOL_ITERATIONS = 15


# ---------------------------------------------------------------------------
# Event types (used for streaming in Phase 9, returned now for structure)
# ---------------------------------------------------------------------------


@dataclass
class ToolCallEvent:
    """Emitted each time the model invokes a tool."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_call_id: uuid.UUID
    status: str  # "executed" | "proposed" | "failed"
    output_summary: str


@dataclass
class HypothesisEvent:
    """Emitted when the model produces its final hypothesis."""

    hypothesis_id: uuid.UUID
    summary: str
    confidence: str
    reasoning: str
    proposed_actions: list[dict[str, str]]


@dataclass
class ErrorEvent:
    """Emitted when the orchestrator hits an unrecoverable error."""

    message: str


InvestigationEvent = ToolCallEvent | HypothesisEvent | ErrorEvent


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------


def _parse_final_response(text: str) -> dict[str, Any]:
    """Parse the structured HYPOTHESIS/CONFIDENCE/PROPOSED_ACTIONS block.

    Returns a dict with keys: summary, confidence, reasoning, proposed_actions.
    proposed_actions is a list of {"action", "reason", "evidence"} dicts.
    """
    result: dict[str, Any] = {
        "summary": "",
        "confidence": "low",
        "reasoning": "",
        "proposed_actions": [],
    }

    # Extract HYPOTHESIS block
    hyp_match = re.search(r"HYPOTHESIS:\s*\n(.*?)(?=\nCONFIDENCE:)", text, re.DOTALL | re.IGNORECASE)
    if hyp_match:
        result["summary"] = hyp_match.group(1).strip()

    # Extract CONFIDENCE
    conf_match = re.search(r"CONFIDENCE:\s*(low|medium|high)", text, re.IGNORECASE)
    if conf_match:
        result["confidence"] = conf_match.group(1).lower()

    # Extract REASONING
    reasoning_match = re.search(r"REASONING:\s*\n?(.*?)(?=\nPROPOSED_ACTIONS:|\Z)", text, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        result["reasoning"] = reasoning_match.group(1).strip()

    # Extract PROPOSED_ACTIONS block
    actions_match = re.search(r"PROPOSED_ACTIONS:\s*\n(.*)", text, re.DOTALL | re.IGNORECASE)
    if actions_match:
        actions_text = actions_match.group(1).strip()
        if actions_text.lower() == "none":
            result["proposed_actions"] = []
        else:
            # Parse each "- ACTION: ... REASON: ... EVIDENCE: ..." block
            action_blocks = re.split(r"\n(?=- ACTION:)", actions_text)
            for block in action_blocks:
                action_m = re.search(r"ACTION:\s*(\S+)", block, re.IGNORECASE)
                reason_m = re.search(r"REASON:\s*(.*?)(?=\n\s*EVIDENCE:|\Z)", block, re.DOTALL | re.IGNORECASE)
                evidence_m = re.search(r"EVIDENCE:\s*(.*?)(?=\n- ACTION:|\Z)", block, re.DOTALL | re.IGNORECASE)
                if action_m:
                    result["proposed_actions"].append(
                        {
                            "action": action_m.group(1).strip(),
                            "reason": reason_m.group(1).strip() if reason_m else "",
                            "evidence": evidence_m.group(1).strip() if evidence_m else "",
                        }
                    )

    # Fallback: if we couldn't parse, treat the whole text as the summary
    if not result["summary"] and text.strip():
        result["summary"] = text.strip()

    return result


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------


def _save_evidence(
    db: Session,
    incident_id: uuid.UUID,
    tool_call: ToolCall,
    tool_name: str,
    tool_output: dict[str, Any],
) -> Evidence:
    """Persist an evidence row from a tool result."""
    # Map tool name to evidence type
    type_map = {
        "query_logs": "log",
        "get_metrics": "metric",
        "get_recent_deploys": "deploy",
        "search_runbooks": "runbook",
        "get_service_status": "log",  # service status is derived from metrics
    }
    evidence_type = type_map.get(tool_name, "log")

    # Build a human-readable summary of what was found
    summary = _summarise_tool_output(tool_name, tool_output)

    evidence = Evidence(
        incident_id=incident_id,
        tool_call_id=tool_call.id,
        evidence_type=evidence_type,
        summary=summary,
        raw_ref=json.dumps({"tool": tool_name, "tool_call_id": str(tool_call.id)}),
    )
    db.add(evidence)
    db.flush()
    return evidence


def _summarise_tool_output(tool_name: str, output: dict[str, Any]) -> str:
    """One-line summary of a tool result for the evidence table."""
    if tool_name == "query_logs":
        count = output.get("count", 0)
        service = output.get("service", "")
        return f"{count} log entries for {service}"
    if tool_name == "get_metrics":
        service = output.get("service", "")
        metric = output.get("metric_name", "")
        count = output.get("count", 0)
        return f"{count} data points for {service}/{metric}"
    if tool_name == "get_recent_deploys":
        count = output.get("count", 0)
        service = output.get("service", "")
        return f"{count} recent deploys for {service}"
    if tool_name == "search_runbooks":
        count = output.get("count", 0)
        query = output.get("query", "")
        return f"{count} runbook results for query: {query!r}"
    if tool_name == "get_service_status":
        service = output.get("service", "")
        status = output.get("status", "unknown")
        rate = output.get("latest_error_rate")
        return f"{service} status={status} error_rate={rate}"
    return f"Tool {tool_name} result"


def _write_audit(db: Session, incident_id: uuid.UUID, action: str, detail: dict) -> None:
    db.add(
        AuditLog(
            incident_id=incident_id,
            actor="system",
            action=action,
            detail_json=json.dumps(detail, default=str),
        )
    )


# ---------------------------------------------------------------------------
# Proposed-action validation
# ---------------------------------------------------------------------------


def _validate_proposed_action(
    action_name: str,
    action_reason: str,
    action_evidence_text: str,
    evidence_ids: list[uuid.UUID],
) -> bool:
    """A side-effecting action proposal is rejected here (at the orchestration
    layer) if it cites no evidence.  This is spec §8 rule 4, enforced in code.
    """
    from app.tools.registry import TOOLS

    tool = TOOLS.get(action_name)
    if tool is None:
        logger.warning("Proposed unknown tool: %s — rejected", action_name)
        return False
    if not tool.is_side_effecting:
        # Read-only tools should not be in PROPOSED_ACTIONS
        return False
    if not action_evidence_text.strip() and not evidence_ids:
        logger.warning("Side-effecting proposal %s has no evidence — rejected", action_name)
        return False
    if not action_reason.strip():
        logger.warning("Side-effecting proposal %s has no reason — rejected", action_name)
        return False
    return True


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_investigation(
    db: Session,
    incident: Incident,
) -> Generator[InvestigationEvent, None, None]:
    """Run the full investigation loop for an incident.

    This is a generator so that Phase 9 can stream events to the client
    via SSE as they happen.  Callers that don't need streaming can simply
    exhaust the generator: list(run_investigation(db, incident)).

    All DB writes happen inside this function.  The caller must not commit
    between yields — we flush after every write and do a final commit at
    the end.
    """
    incident_id = incident.id
    logger.info("Investigation started | incident_id=%s", incident_id)

    # Update incident status
    incident.status = "investigating"
    db.flush()

    _write_audit(db, incident_id, "investigation_started", {"incident_id": str(incident_id)})

    # Build the conversation and tool schemas
    messages = build_initial_messages(incident.title, incident.description)
    tool_schemas = build_tool_schemas()

    # Track evidence rows created during this investigation so we can link
    # them to the hypothesis citations later.
    all_evidence: list[Evidence] = []

    # Tool-call loop --------------------------------------------------------
    iterations = 0
    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1

        try:
            response: ProviderResponse = call_llm(messages, tool_schemas)
        except Exception as exc:
            logger.exception("LLM call failed | incident_id=%s", incident_id)
            incident.status = "investigating"  # leave open for retry
            db.commit()
            yield ErrorEvent(message=f"LLM error: {exc}")
            return

        # No tool calls → model is done, go to hypothesis parsing
        if not response.tool_calls:
            break

        # Process each tool call the model requested for this LLM turn.
        # tool_results accumulates (request, formatted_result) pairs so we can
        # build the correct OpenAI multi-call message format after the loop.
        tool_results: list[tuple] = []
        for tc_req in response.tool_calls:
            from app.tools.executor import call_tool

            logger.info(
                "Tool call | incident_id=%s tool=%s args=%s",
                incident_id,
                tc_req.name,
                tc_req.arguments,
            )

            # call_tool persists the input before running anything (spec §8)
            tool_call_row = call_tool(db, incident_id, tc_req.name, tc_req.arguments)

            # Build the output dict for context formatting
            if tool_call_row.tool_output_json:
                try:
                    output = json.loads(tool_call_row.tool_output_json)
                except json.JSONDecodeError:
                    output = {"raw": tool_call_row.tool_output_json}
            else:
                output = {}

            # Persist evidence (only for executed read-only calls with real output)
            evidence_row: Evidence | None = None
            if tool_call_row.status == "executed" and not tool_call_row.is_side_effecting:
                evidence_row = _save_evidence(db, incident_id, tool_call_row, tc_req.name, output)
                all_evidence.append(evidence_row)

            _write_audit(
                db,
                incident_id,
                "tool_call",
                {
                    "tool_call_id": str(tool_call_row.id),
                    "tool_name": tc_req.name,
                    "status": tool_call_row.status,
                    "is_side_effecting": tool_call_row.is_side_effecting,
                },
            )

            # Format result for the model's next turn
            if tool_call_row.status == "proposed":
                # Side-effecting tool was just queued, not run.
                tool_result_text = (
                    f"This action has been queued for human approval and has NOT been executed yet. "
                    f"Tool: {tc_req.name}"
                )
            elif output.get("error"):
                tool_result_text = f"Tool error: {output['error']}"
            else:
                tool_result_text = format_tool_result_for_context(tc_req.name, output)

            output_summary = (
                tool_result_text[:200] + "..." if len(tool_result_text) > 200 else tool_result_text
            )


            yield ToolCallEvent(
                tool_name=tc_req.name,
                tool_input=tc_req.arguments,
                tool_call_id=tool_call_row.id,
                status=tool_call_row.status,
                output_summary=output_summary,
            )

            # Collect tool results; we'll append messages after processing all calls
            tool_results.append((tc_req, tool_result_text))

        # OpenAI requires ONE assistant message with ALL tool calls, followed
        # by one tool-result message per call.  Building a new assistant message
        # per tool call would produce malformed history and a 400 from the API.
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc_req.id,
                        "type": "function",
                        "function": {
                            "name": tc_req.name,
                            "arguments": json.dumps(tc_req.arguments),
                        },
                    }
                    for tc_req, _ in tool_results
                ],
            }
        )
        for tc_req, result_text in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_req.id,
                    "content": result_text,
                }
            )


    # Hypothesis parsing ----------------------------------------------------
    final_text = response.content or ""

    if not final_text.strip():
        incident.status = "investigating"
        db.commit()
        yield ErrorEvent(message="Model returned no hypothesis text after tool calls.")
        return

    parsed = _parse_final_response(final_text)

    # Validate proposed side-effecting actions before storing
    valid_proposed_actions = []
    evidence_ids = [e.id for e in all_evidence]
    for pa in parsed.get("proposed_actions", []):
        if _validate_proposed_action(pa["action"], pa["reason"], pa["evidence"], evidence_ids):
            valid_proposed_actions.append(pa)
        else:
            logger.info(
                "Proposed action rejected at orchestration layer | action=%s incident=%s",
                pa["action"],
                incident_id,
            )

    # Persist hypothesis
    hypothesis = Hypothesis(
        incident_id=incident_id,
        summary=parsed["summary"],
        confidence=parsed["confidence"],
        reasoning=parsed["reasoning"],
    )
    db.add(hypothesis)
    db.flush()

    # Link all collected evidence to the hypothesis
    for ev in all_evidence:
        db.add(HypothesisCitation(hypothesis_id=hypothesis.id, evidence_id=ev.id))

    # Persist validated proposed side-effecting actions as ToolCall proposals
    # They will appear in the UI for human review (Phase 6 wires the endpoints).
    for pa in valid_proposed_actions:
        from app.tools.executor import call_tool

        # We call call_tool with the action name and a stub input.
        # For now the input only carries reason; Phase 6 will pass full args.
        call_tool(
            db,
            incident_id,
            pa["action"],
            {"reason": pa["reason"], "_evidence": pa["evidence"]},
        )

    # Update incident status
    incident.status = "hypothesis_ready" if not valid_proposed_actions else "action_pending"
    incident.resolved_at = None  # clear any stale value

    _write_audit(
        db,
        incident_id,
        "hypothesis_generated",
        {
            "hypothesis_id": str(hypothesis.id),
            "confidence": parsed["confidence"],
            "evidence_count": len(all_evidence),
            "proposed_actions": len(valid_proposed_actions),
        },
    )

    db.commit()
    logger.info(
        "Investigation complete | incident_id=%s hypothesis_id=%s confidence=%s",
        incident_id,
        hypothesis.id,
        parsed["confidence"],
    )

    yield HypothesisEvent(
        hypothesis_id=hypothesis.id,
        summary=parsed["summary"],
        confidence=parsed["confidence"],
        reasoning=parsed["reasoning"],
        proposed_actions=valid_proposed_actions,
    )
