"""Tests for the agent orchestrator (Phase 5).

We mock the LLM provider so these tests never make a real API call.
The tests verify:
  1. A successful investigation loop produces a Hypothesis with citations.
  2. Evidence is stored for every executed tool call.
  3. Side-effecting proposals without evidence are rejected by the orchestrator.
  4. The iterate-cap prevents infinite loops.
  5. An LLM error yields an ErrorEvent (not a crash).
  6. The parse_final_response helper extracts all structured fields.
"""

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.agent.orchestrator import (
    ErrorEvent,
    HypothesisEvent,
    ToolCallEvent,
    _parse_final_response,
    run_investigation,
)
from app.agent.provider import ProviderResponse, ToolCallRequest
from app.models import Evidence, Hypothesis, Incident, ToolCall, User
from app.seed import seed_services


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_incident(db: Session, title: str = "Checkout returning 500s") -> Incident:
    user = User(email=f"oncall+{uuid.uuid4()}@example.com", hashed_password="x", display_name="On Call")
    db.add(user)
    db.flush()
    incident = Incident(user_id=user.id, title=title, description="users seeing 500s")
    db.add(incident)
    db.flush()
    return incident


def _make_tool_call_req(name: str, args: dict) -> ToolCallRequest:
    return ToolCallRequest(id=str(uuid.uuid4()), name=name, arguments=args)


# ---------------------------------------------------------------------------
# Tests for _parse_final_response
# ---------------------------------------------------------------------------


def test_parse_full_structured_response() -> None:
    text = """
HYPOTHESIS:
The checkout service started returning 500s at 14:32, three minutes after deploy a1b2c3.
The error logs show NullPointerException in PaymentProcessor.

CONFIDENCE: high
REASONING: Deploy timestamp closely precedes error spike; runbook section 12-40 describes this exact pattern.

PROPOSED_ACTIONS:
- ACTION: rollback_deploy
  REASON: Deploy a1b2c3 introduced the error
  EVIDENCE: deploy record sha=a1b2c3 at 14:29; error spike at 14:32
"""
    result = _parse_final_response(text)
    assert "checkout service" in result["summary"]
    assert result["confidence"] == "high"
    assert "Deploy timestamp" in result["reasoning"]
    assert len(result["proposed_actions"]) == 1
    action = result["proposed_actions"][0]
    assert action["action"] == "rollback_deploy"
    assert "a1b2c3" in action["evidence"]


def test_parse_no_proposed_actions() -> None:
    text = """
HYPOTHESIS:
High memory usage, no clear root cause yet.

CONFIDENCE: low
REASONING: Need more data.

PROPOSED_ACTIONS:
none
"""
    result = _parse_final_response(text)
    assert result["proposed_actions"] == []
    assert result["confidence"] == "low"


def test_parse_fallback_for_unstructured_response() -> None:
    text = "The system appears to be having memory issues."
    result = _parse_final_response(text)
    assert "memory issues" in result["summary"]
    assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# Tests for run_investigation
# ---------------------------------------------------------------------------


class _MockProvider:
    """Mimics the agent provider.  Configure via class attributes before test."""

    responses: list[ProviderResponse] = []
    _call_count: int = 0

    @classmethod
    def reset(cls, responses: list[ProviderResponse]) -> None:
        cls.responses = list(responses)
        cls._call_count = 0

    @classmethod
    def call(cls, messages, tool_schemas, *, model=None) -> ProviderResponse:
        idx = cls._call_count
        cls._call_count += 1
        if idx < len(cls.responses):
            return cls.responses[idx]
        # Default: no tool calls, no content → ErrorEvent in orchestrator
        return ProviderResponse(content=None, tool_calls=[])


GOOD_HYPOTHESIS = (
    "HYPOTHESIS:\nThe error spike at 14:32 followed deploy a1b2c3 by three minutes.\n\n"
    "CONFIDENCE: high\n"
    "REASONING: Strong temporal correlation; runbook confirms this pattern.\n\n"
    "PROPOSED_ACTIONS:\n"
    "- ACTION: rollback_deploy\n"
    "  REASON: Deploy a1b2c3 introduced the error\n"
    "  EVIDENCE: deploy sha=a1b2c3; error spike at 14:32"
)


def test_successful_investigation_produces_hypothesis(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    # LLM first calls get_service_status, then returns hypothesis
    _MockProvider.reset(
        [
            ProviderResponse(
                content=None,
                tool_calls=[_make_tool_call_req("get_service_status", {"service": "checkout-service"})],
            ),
            ProviderResponse(content=GOOD_HYPOTHESIS, tool_calls=[]),
        ]
    )
    monkeypatch.setattr("app.agent.orchestrator.call_llm", _MockProvider.call)

    events = list(run_investigation(db_session, incident))

    tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
    hyp_events = [e for e in events if isinstance(e, HypothesisEvent)]
    error_events = [e for e in events if isinstance(e, ErrorEvent)]

    assert len(error_events) == 0, f"Unexpected errors: {error_events}"
    assert len(tool_events) == 1
    assert tool_events[0].tool_name == "get_service_status"
    assert tool_events[0].status == "executed"
    assert len(hyp_events) == 1
    assert hyp_events[0].confidence == "high"


def test_evidence_is_stored_for_each_executed_tool_call(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    _MockProvider.reset(
        [
            ProviderResponse(
                content=None,
                tool_calls=[
                    _make_tool_call_req("get_service_status", {"service": "checkout-service"}),
                    _make_tool_call_req("search_runbooks", {"query": "checkout 500"}),
                ],
            ),
            ProviderResponse(
                content=(
                    "HYPOTHESIS:\nSomething broke.\n\nCONFIDENCE: low\n"
                    "REASONING: Limited data.\n\nPROPOSED_ACTIONS:\nnone"
                ),
                tool_calls=[],
            ),
        ]
    )
    monkeypatch.setattr("app.agent.orchestrator.call_llm", _MockProvider.call)

    list(run_investigation(db_session, incident))

    evidence_rows = db_session.query(Evidence).filter(Evidence.incident_id == incident.id).all()
    # Both tools are read-only and should produce evidence rows
    assert len(evidence_rows) == 2
    types = {e.evidence_type for e in evidence_rows}
    assert "log" in types or "runbook" in types  # service_status → "log"; runbooks → "runbook"


def test_hypothesis_is_stored_in_db(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    _MockProvider.reset([ProviderResponse(content=GOOD_HYPOTHESIS, tool_calls=[])])
    monkeypatch.setattr("app.agent.orchestrator.call_llm", _MockProvider.call)

    list(run_investigation(db_session, incident))

    hyp = db_session.query(Hypothesis).filter(Hypothesis.incident_id == incident.id).first()
    assert hyp is not None
    assert hyp.confidence == "high"
    assert "error spike" in hyp.summary


def test_side_effecting_proposal_without_evidence_is_rejected(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §8 rule 4: a side-effecting proposal with no cited evidence must
    be rejected at the orchestration layer before reaching the UI.
    """
    seed_services(db_session)
    incident = _make_incident(db_session)

    bad_hypothesis = (
        "HYPOTHESIS:\nSomething is wrong.\n\nCONFIDENCE: low\nREASONING: Gut feeling.\n\n"
        "PROPOSED_ACTIONS:\n"
        "- ACTION: rollback_deploy\n"
        "  REASON: Just try it\n"
        "  EVIDENCE: "  # empty evidence
    )
    _MockProvider.reset([ProviderResponse(content=bad_hypothesis, tool_calls=[])])
    monkeypatch.setattr("app.agent.orchestrator.call_llm", _MockProvider.call)

    events = list(run_investigation(db_session, incident))

    hyp_events = [e for e in events if isinstance(e, HypothesisEvent)]
    assert len(hyp_events) == 1
    # Action should be filtered out (no evidence text and no evidence rows)
    assert len(hyp_events[0].proposed_actions) == 0

    # Also verify no rollback_deploy ToolCall was written as a proposal
    proposed_calls = (
        db_session.query(ToolCall)
        .filter(
            ToolCall.incident_id == incident.id,
            ToolCall.tool_name == "rollback_deploy",
            ToolCall.status == "proposed",
        )
        .all()
    )
    assert len(proposed_calls) == 0


def test_llm_error_yields_error_event(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    def _failing_call(messages, tool_schemas, *, model=None):
        raise RuntimeError("API quota exceeded")

    monkeypatch.setattr("app.agent.orchestrator.call_llm", _failing_call)

    events = list(run_investigation(db_session, incident))

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) == 1
    assert "API quota exceeded" in error_events[0].message


def test_investigation_respects_max_iterations_cap(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the model keeps requesting tools without ever producing a final
    response, the orchestrator must stop after MAX_TOOL_ITERATIONS.
    """
    from app.agent import orchestrator as orch

    seed_services(db_session)
    incident = _make_incident(db_session)

    # Always return a tool call → forces the loop to run until the cap
    def _infinite_tool(messages, tool_schemas, *, model=None):
        return ProviderResponse(
            content=None,
            tool_calls=[_make_tool_call_req("get_service_status", {"service": "checkout-service"})],
        )

    monkeypatch.setattr("app.agent.orchestrator.call_llm", _infinite_tool)
    monkeypatch.setattr(orch, "MAX_TOOL_ITERATIONS", 3)  # lower cap for speed

    events = list(run_investigation(db_session, incident))

    # Should get 3 tool events (one per iteration) then an error event
    tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(tool_events) == 3
    assert len(error_events) == 1


def test_incident_status_updates_correctly(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_services(db_session)
    incident = _make_incident(db_session)

    # No proposed actions → status should be hypothesis_ready
    no_action_hypothesis = (
        "HYPOTHESIS:\nNormal traffic spike.\n\nCONFIDENCE: medium\n"
        "REASONING: No anomalous deploys found.\n\nPROPOSED_ACTIONS:\nnone"
    )
    _MockProvider.reset([ProviderResponse(content=no_action_hypothesis, tool_calls=[])])
    monkeypatch.setattr("app.agent.orchestrator.call_llm", _MockProvider.call)

    list(run_investigation(db_session, incident))

    db_session.refresh(incident)
    assert incident.status == "hypothesis_ready"
