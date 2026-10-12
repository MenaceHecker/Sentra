import json
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import ToolCall
from app.tools.registry import TOOLS


def call_tool(db: Session, incident_id: uuid.UUID, tool_name: str, tool_input: dict[str, Any]) -> ToolCall:
    """The orchestration-layer gate from spec Section 8. This function, not
    the model and not a prompt, decides whether a tool call runs right away
    or just gets recorded as a proposal. Every attempt is persisted with its
    exact raw input before anything else happens, including unknown tool
    names and invalid input, so the trail can't be edited by a later model
    turn and a bad call is itself visible in the audit log.

    A side-effecting tool is never executed here. It's written down as
    "proposed" and the function stops, full stop. Nothing calls its
    implementation until a human approves it (Phase 6)."""
    tool = TOOLS.get(tool_name)

    call = ToolCall(
        incident_id=incident_id,
        tool_name=tool_name,
        tool_input_json=json.dumps(tool_input, default=str),
        is_side_effecting=tool.is_side_effecting if tool is not None else False,
        status="proposed",
    )
    db.add(call)
    db.flush()  # persisted before we know whether it will even run

    if tool is None:
        call.status = "failed"
        call.tool_output_json = json.dumps({"error": f"unknown tool: {tool_name}"})
        call.executed_at = datetime.now(UTC)
        db.commit()
        db.refresh(call)
        return call

    try:
        validated_input = tool.input_model.model_validate(tool_input)
    except ValidationError as exc:
        call.status = "failed"
        call.tool_output_json = json.dumps({"error": str(exc)})
        call.executed_at = datetime.now(UTC)
        db.commit()
        db.refresh(call)
        return call

    if tool.is_side_effecting:
        db.commit()
        db.refresh(call)
        return call

    try:
        output = tool.run(db, validated_input)
        call.tool_output_json = json.dumps(output, default=str)
        call.status = "executed"
    except Exception as exc:
        call.tool_output_json = json.dumps({"error": str(exc)})
        call.status = "failed"
    call.executed_at = datetime.now(UTC)

    db.commit()
    db.refresh(call)
    return call


def execute_approved_call(db: Session, call: ToolCall) -> ToolCall:
    """Runs a side-effecting tool call a human has just approved. This is
    the only place a side-effecting tool's implementation ever actually
    runs, separate from call_tool() above on purpose: call_tool's whole
    job is deciding whether a NEW call gets to run immediately or just
    gets written down, and a side-effecting call always takes the second
    path there. This function is what finishes the job later, once a
    human approval record exists, called only from the approve endpoint
    after it has already stamped decided_at/decided_by_user_id. It does
    not commit, the caller controls that transaction so the approval
    decision, the execution outcome, and the incident status update all
    land together or not at all."""
    tool = TOOLS[call.tool_name]
    validated_input = tool.input_model.model_validate(json.loads(call.tool_input_json))

    try:
        output = tool.run(db, validated_input)
        call.tool_output_json = json.dumps(output, default=str)
        call.status = "executed"
    except Exception as exc:
        call.tool_output_json = json.dumps({"error": str(exc)})
        call.status = "failed"
    call.executed_at = datetime.now(UTC)

    return call
