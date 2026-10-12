"""Agent orchestrator — the core of Sentra.

This module runs the LLM tool-calling loop for a single investigation:

  1. Build initial messages from the incident description.
  2. Call the LLM.
  3. For each tool call the model requests:
       a. Route through call_tool() (the approval-gate layer from Phase 4).
       b. If it's a side-effecting proposal with no evidence gathered yet
          this investigation, downgrade it to "failed" right here, before
          a human ever sees it (spec §8 rule 4).
       c. Store the tool call and its output as Evidence in the DB (read-only
          tools only, a proposal isn't evidence of anything).
       d. Append the tool result to the message history.
  4. Repeat until the model returns a final response (no tool calls).
  5. Parse the structured HYPOTHESIS / CONFIDENCE / REASONING block.
  6. Write the Hypothesis + HypothesisCitations to the DB. Proposed
     side-effecting actions are the ToolCall rows already persisted in
     step 3 with status "proposed", there's no separate proposal record.
  7. Write an AuditLog entry for the full investigation run.
  8. Yield InvestigationEvent objects for SSE streaming (Phase 9 will use them).

Key design constraints from spec §8:
  - The distinction between read-only and side-effecting tools is enforced
    in call_tool(), never here or in the prompt.
  - Every tool call (input + output) is persisted before the model sees
    the result.
  - A side-effecting proposal is made via a normal tool call (the model
    gets the real input schema, so it can't omit required fields), and is
    rejected here if no evidence has been gathered yet this investigation.
  - Max iterations cap prevents infinite loops / runaway cost.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agent.context import format_tool_result_for_context
from app.agent.prompts import build_initial_messages, build_tool_schemas
from app.agent.provider import ProviderResponse, call_llm
from app.audit import write_audit, write_status_change
from app.models import Evidence, Hypothesis, HypothesisCitation, Incident, ToolCall
from app.tools.executor import call_tool

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
    """Emitted when the model produces its final hypothesis.

    proposed_actions reflects the real ToolCall rows left in "proposed"
    status by this investigation, there's no separate text-parsed version
    of this list, what's here is exactly what a human would see to approve
    or reject.
    """

    hypothesis_id: uuid.UUID
    summary: str
    confidence: str
    reasoning: str
    proposed_actions: list[dict[str, Any]]


@dataclass
class ErrorEvent:
    """Emitted when the orchestrator hits an unrecoverable error."""

    message: str


InvestigationEvent = ToolCallEvent | HypothesisEvent | ErrorEvent


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------


def _parse_final_response(text: str) -> dict[str, Any]:
    """Parse the structured HYPOTHESIS/CONFIDENCE/REASONING block.

    Returns a dict with keys: summary, confidence, reasoning. Side-effecting
    proposals aren't parsed from this text, they're real tool calls the
    model makes during the loop (see run_investigation), so there's nothing
    here to extract for them.
    """
    result: dict[str, Any] = {
        "summary": "",
        "confidence": "low",
        "reasoning": "",
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
    reasoning_match = re.search(r"REASONING:\s*\n?(.*)", text, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        result["reasoning"] = reasoning_match.group(1).strip()

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
    old_status = incident.status
    incident.status = "investigating"
    db.flush()

    write_audit(db, incident_id, "system", "investigation_started", {"incident_title": incident.title})
    write_status_change(db, incident_id, "system", old_status, incident.status)

    # Build the conversation and tool schemas
    messages = build_initial_messages(incident.title, incident.description)
    tool_schemas = build_tool_schemas()

    # Track evidence rows created during this investigation so we can link
    # them to the hypothesis citations later.
    all_evidence: list[Evidence] = []
    # Side-effecting tool calls that are still "proposed" once the loop
    # ends, i.e. what a human actually needs to approve or reject.
    proposed_tool_calls: list[ToolCall] = []

    # Tool-call loop --------------------------------------------------------
    iterations = 0
    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1

        try:
            response: ProviderResponse = call_llm(messages, tool_schemas)
        except Exception as exc:
            logger.exception("LLM call failed | incident_id=%s", incident_id)
            write_audit(db, incident_id, "system", "llm_error", {"message": str(exc), "iteration": iterations})
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
            logger.info(
                "Tool call | incident_id=%s tool=%s args=%s",
                incident_id,
                tc_req.name,
                tc_req.arguments,
            )

            # call_tool persists the input before running anything (spec §8)
            tool_call_row = call_tool(db, incident_id, tc_req.name, tc_req.arguments)

            # Spec §8 rule 4: a side-effecting proposal with no evidence
            # gathered yet this investigation is rejected right here, before
            # a human ever sees it. This happens before the output dict
            # below is built, so the rejection message flows straight back
            # to the model like any other tool error.
            if tool_call_row.is_side_effecting and tool_call_row.status == "proposed" and not all_evidence:
                logger.info(
                    "Side-effecting proposal rejected, no evidence yet | incident_id=%s tool=%s",
                    incident_id,
                    tc_req.name,
                )
                tool_call_row.status = "failed"
                tool_call_row.tool_output_json = json.dumps(
                    {"error": "rejected: no evidence has been gathered yet this investigation"}
                )
                tool_call_row.executed_at = datetime.now(UTC)
                db.flush()

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
            elif tool_call_row.status == "proposed" and tool_call_row.is_side_effecting:
                proposed_tool_calls.append(tool_call_row)

            # Snapshot the actual input and output here, not just status
            # and an id, so the audit trail alone has everything needed to
            # reconstruct what happened even if tool_calls changed later.
            write_audit(
                db,
                incident_id,
                "system",
                "tool_call",
                {
                    "tool_call_id": str(tool_call_row.id),
                    "tool_name": tc_req.name,
                    "tool_input": tc_req.arguments,
                    "tool_output": output,
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

            output_summary = tool_result_text[:200] + "..." if len(tool_result_text) > 200 else tool_result_text

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
                        "provider_metadata": tc_req.provider_metadata,
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
        write_audit(db, incident_id, "system", "llm_error", {"message": "no hypothesis text after tool calls"})
        incident.status = "investigating"
        db.commit()
        yield ErrorEvent(message="Model returned no hypothesis text after tool calls.")
        return

    parsed = _parse_final_response(final_text)

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

    # Update incident status. proposed_tool_calls only holds side-effecting
    # calls that are still "proposed", the ones the evidence check above
    # didn't downgrade to "failed" (see the tool-call loop).
    old_status = incident.status
    incident.status = "action_pending" if proposed_tool_calls else "hypothesis_ready"
    incident.resolved_at = None  # clear any stale value

    write_audit(
        db,
        incident_id,
        "system",
        "hypothesis_generated",
        {
            "hypothesis_id": str(hypothesis.id),
            "summary": parsed["summary"],
            "confidence": parsed["confidence"],
            "reasoning": parsed["reasoning"],
            "evidence_count": len(all_evidence),
            "proposed_action_ids": [str(tc.id) for tc in proposed_tool_calls],
        },
    )
    write_status_change(db, incident_id, "system", old_status, incident.status)

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
        proposed_actions=[
            {
                "tool_call_id": str(tc.id),
                "tool_name": tc.tool_name,
                "tool_input": json.loads(tc.tool_input_json),
            }
            for tc in proposed_tool_calls
        ],
    )
