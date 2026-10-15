"""Phase 11 evaluation harness.

Drives the real backend + simulated system over HTTP, exactly the way a
reviewer clicking through the UI would: register, inject a scenario,
create an incident, investigate it, read back the result. No internals
are reached into directly, so what this measures is what a real user
actually gets.

Usage (both servers already running, see README):
    cd backend && source .venv/bin/activate
    python evaluation/run_eval.py

Writes evaluation/results.json (every run's full raw record) and prints
a markdown summary table to stdout. Nothing here fabricates a result:
every number comes from a real response the backend actually returned
for a real investigation against a real LLM call.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

BACKEND_URL = "http://localhost:8000"
EVAL_EMAIL = "evaluation-harness@example.com"
EVAL_PASSWORD = "evaluation-harness-password"
RUNS_PER_SCENARIO = 2
INGESTION_SETTLE_SECONDS = 15  # backend's own ingestion loop ticks every 10s (app/config.py)

# ---------------------------------------------------------------------------
# Grading rubric
#
# Deterministic, auditable, defined up front rather than judged after the
# fact: a hypothesis counts as "correct" if its summary+reasoning text
# contains any of a scenario's correct_signals (case-insensitive substring
# match), "partial" if it at least names the right area without the
# specific cause, "incorrect" otherwise. This is a simple rubric and says
# so in the README, it's not a claim of rigorous NLP evaluation.
# ---------------------------------------------------------------------------

RUBRIC: dict[str, dict[str, list[str]]] = {
    "checkout-500s": {
        "correct_signals": ["shipping_method", "shipping method"],
        "partial_signals": ["checkout", "deploy", "schema"],
    },
    "checkout-slow-carrier": {
        "correct_signals": ["shipping-rate-carrier", "shipping rate carrier", "carrier"],
        "partial_signals": ["latency", "slow", "checkout"],
    },
    "payments-timeout": {
        "correct_signals": ["connection pool", "pool exhaust", "connection-pool"],
        "partial_signals": ["payment-provider", "timeout", "payments"],
    },
    "payments-bad-credentials": {
        "correct_signals": ["credential", "api key", "authentication", "401", "unauthorized"],
        "partial_signals": ["payment-provider", "payments"],
    },
    "inventory-oom": {
        "correct_signals": ["memory", "oom", "cache leak", "cache", "eviction"],
        "partial_signals": ["inventory", "worker", "restart"],
    },
    "inventory-db-lock": {
        "correct_signals": ["lock", "deadlock", "database lock"],
        "partial_signals": ["inventory", "reservation", "timeout"],
    },
}


def grade(scenario_id: str, hypothesis_text: str) -> str:
    text = hypothesis_text.lower()
    rubric = RUBRIC[scenario_id]
    if any(sig in text for sig in rubric["correct_signals"]):
        return "correct"
    if any(sig in text for sig in rubric["partial_signals"]):
        return "partial"
    return "incorrect"


@dataclass
class RunResult:
    scenario_id: str
    run_index: int
    incident_id: str
    status_code: int
    error: str | None = None
    hypothesis_summary: str = ""
    hypothesis_reasoning: str = ""
    confidence: str | None = None
    verdict: str | None = None
    tool_call_count: int = 0
    evidence_count: int = 0
    citation_count: int = 0
    citations_valid: bool = True
    side_effecting_calls_auto_executed: int = 0  # should always be 0
    seconds_to_hypothesis: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_call_count: int = 0


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        event_type = "message"
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            events.append((event_type, json.loads("\n".join(data_lines))))
    return events


def _get_token(client: httpx.Client) -> str:
    resp = client.post("/api/auth/register", json={"email": EVAL_EMAIL, "password": EVAL_PASSWORD}, timeout=30)
    if resp.status_code == 409:
        resp = client.post("/api/auth/login", json={"email": EVAL_EMAIL, "password": EVAL_PASSWORD}, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def run_one(client: httpx.Client, headers: dict, scenario_id: str, run_index: int) -> RunResult:
    scenario_resp = client.post(f"/api/scenarios/{scenario_id}/inject", headers=headers, timeout=30)
    scenario_resp.raise_for_status()

    print(f"  [{scenario_id} #{run_index}] injected, waiting {INGESTION_SETTLE_SECONDS}s for ingestion...")
    time.sleep(INGESTION_SETTLE_SECONDS)

    inc_resp = client.post(
        "/api/incidents",
        json={"title": f"[eval] {scenario_id} run {run_index}"},
        headers=headers,
        timeout=30,
    )
    inc_resp.raise_for_status()
    incident_id = inc_resp.json()["id"]

    # A plain (non-streamed) request still works fine here: httpx just reads
    # until the connection closes, same as the SSE response does once its
    # generator is exhausted. We measure total wall-clock for the whole
    # call rather than timing the "hypothesis" SSE frame specifically,
    # since in this architecture the "done" event that closes the stream
    # follows "hypothesis" immediately (just a DB reload in between), so
    # the two are functionally the same moment.
    start = time.monotonic()
    resp = client.post(f"/api/incidents/{incident_id}/investigate", headers=headers, timeout=120)
    seconds_to_hypothesis = time.monotonic() - start
    if resp.status_code != 200:
        return RunResult(
            scenario_id=scenario_id,
            run_index=run_index,
            incident_id=incident_id,
            status_code=resp.status_code,
            error=f"investigate returned {resp.status_code}",
        )
    events = _parse_sse(resp.text)

    done_events = [data for event_type, data in events if event_type == "done"]
    error_events = [data for event_type, data in events if event_type == "error"]
    if not done_events:
        return RunResult(
            scenario_id=scenario_id,
            run_index=run_index,
            incident_id=incident_id,
            status_code=200,
            error=f"stream never sent a done event, errors: {error_events}",
        )

    incident = done_events[0]["incident"]
    hypotheses = incident["hypotheses"]
    if not hypotheses:
        return RunResult(
            scenario_id=scenario_id,
            run_index=run_index,
            incident_id=incident_id,
            status_code=200,
            error=f"no hypothesis produced, errors: {error_events}",
            tool_call_count=len(incident["tool_calls"]),
        )
    hyp = hypotheses[-1]

    valid_evidence_ids = {e["id"] for e in incident["evidence"]}
    citations = hyp["citations"]
    citations_valid = all(c["evidence_id"] in valid_evidence_ids for c in citations)

    auto_executed = sum(1 for tc in incident["tool_calls"] if tc["is_side_effecting"] and tc["status"] == "executed")

    audit_resp = client.get(f"/api/incidents/{incident_id}/audit-log", headers=headers, timeout=30)
    audit_resp.raise_for_status()
    llm_calls = [e for e in audit_resp.json() if e["action"] == "llm_call"]
    prompt_tokens = sum(json.loads(e["detail_json"])["prompt_tokens"] for e in llm_calls)
    completion_tokens = sum(json.loads(e["detail_json"])["completion_tokens"] for e in llm_calls)

    hypothesis_text = f"{hyp['summary']} {hyp['reasoning'] or ''}"
    verdict = grade(scenario_id, hypothesis_text)

    return RunResult(
        scenario_id=scenario_id,
        run_index=run_index,
        incident_id=incident_id,
        status_code=200,
        hypothesis_summary=hyp["summary"],
        hypothesis_reasoning=hyp["reasoning"] or "",
        confidence=hyp["confidence"],
        verdict=verdict,
        tool_call_count=len(incident["tool_calls"]),
        evidence_count=len(incident["evidence"]),
        citation_count=len(citations),
        citations_valid=citations_valid,
        side_effecting_calls_auto_executed=auto_executed,
        seconds_to_hypothesis=seconds_to_hypothesis,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        llm_call_count=len(llm_calls),
    )


def main() -> None:
    results: list[RunResult] = []
    with httpx.Client(base_url=BACKEND_URL) as client:
        token = _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        for scenario_id in RUBRIC:
            for run_index in range(1, RUNS_PER_SCENARIO + 1):
                print(f"Running {scenario_id} #{run_index}...")
                try:
                    result = run_one(client, headers, scenario_id, run_index)
                except httpx.HTTPError as exc:
                    result = RunResult(
                        scenario_id=scenario_id,
                        run_index=run_index,
                        incident_id="",
                        status_code=0,
                        error=str(exc),
                    )
                results.append(result)
                print(f"    -> {result.verdict or result.error}")

            client.post(f"/api/scenarios/{scenario_id}/reset", headers=headers, timeout=30)

    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps([asdict(r) for r in results], indent=2, default=str))
    print(f"\nWrote {len(results)} run records to {out_path}")

    print_summary(results)


def print_summary(results: list[RunResult]) -> None:
    ok = [r for r in results if r.error is None]
    print("\n" + "=" * 70)
    print(f"Completed runs: {len(ok)}/{len(results)}")
    if not ok:
        return

    verdict_counts: dict[str, int] = {}
    for r in ok:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
    print(f"Verdicts: {verdict_counts}")

    citation_valid_count = sum(1 for r in ok if r.citations_valid)
    print(f"Citation integrity: {citation_valid_count}/{len(ok)} runs had 100% structurally valid citations")

    bypasses = sum(r.side_effecting_calls_auto_executed for r in ok)
    print(f"Approval-gate bypasses: {bypasses} (should always be 0)")

    times = [r.seconds_to_hypothesis for r in ok if r.seconds_to_hypothesis is not None]
    if times:
        avg, lo, hi = sum(times) / len(times), min(times), max(times)
        print(f"Time to first hypothesis: avg={avg:.1f}s min={lo:.1f}s max={hi:.1f}s")

    total_prompt = sum(r.prompt_tokens for r in ok)
    total_completion = sum(r.completion_tokens for r in ok)
    print(f"Total tokens: prompt={total_prompt} completion={total_completion}")
    print(f"Avg tokens/investigation: prompt={total_prompt / len(ok):.0f} completion={total_completion / len(ok):.0f}")

    print("\nPer-scenario:")
    by_scenario: dict[str, list[RunResult]] = {}
    for r in ok:
        by_scenario.setdefault(r.scenario_id, []).append(r)
    for scenario_id, runs in by_scenario.items():
        verdicts = [r.verdict for r in runs]
        confs = [r.confidence for r in runs]
        print(f"  {scenario_id}: verdicts={verdicts} confidence={confs}")


if __name__ == "__main__":
    main()
