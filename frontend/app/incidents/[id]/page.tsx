"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ProposedActionCard } from "@/components/ProposedActionCard";
import * as api from "@/lib/api";
import type { IncidentDetailOut } from "@/lib/types";

interface LiveEvent {
  id: string;
  kind: "tool_call" | "hypothesis" | "error";
  label: string;
}

function InvestigationWorkspace() {
  const params = useParams();
  const incidentId = params.id as string;

  const [incident, setIncident] = useState<IncidentDetailOut | null>(null);
  const [investigating, setInvestigating] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIncident(await api.getIncident(incidentId));
    } catch {
      setIncident(null);
    }
  }, [incidentId]);

  useEffect(() => {
    refresh();
    return () => abortRef.current?.abort();
  }, [refresh]);

  async function handleInvestigate() {
    setInvestigating(true);
    setError(null);
    setLiveEvents([]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      // streamInvestigation resolves with the fully refreshed incident once
      // the "done" event arrives, so setting it directly avoids a redundant
      // GET. Along the way, onToolCall/onHypothesis/onError fill liveEvents
      // so the timeline updates as each step actually happens instead of
      // sitting on a spinner until the whole investigation finishes.
      const response = await api.streamInvestigation(
        incidentId,
        {
          onToolCall: (event) => {
            const side = event.status === "proposed" ? " (awaiting approval)" : "";
            setLiveEvents((prev) => [
              ...prev,
              { id: event.tool_call_id, kind: "tool_call", label: `${event.tool_name}${side}` },
            ]);
          },
          onHypothesis: (event) => {
            setLiveEvents((prev) => [
              ...prev,
              {
                id: event.hypothesis_id,
                kind: "hypothesis",
                label: `Hypothesis formed (confidence: ${event.confidence})`,
              },
            ]);
          },
          onError: (event) => {
            setLiveEvents((prev) => [...prev, { id: `error-${prev.length}`, kind: "error", label: event.message }]);
          },
        },
        controller.signal,
      );
      setIncident(response.incident);
    } catch (err) {
      setError(
        err instanceof api.ApiError
          ? err.message
          : "Investigation failed. It may need an LLM_PROVIDER key configured on the backend.",
      );
    } finally {
      setInvestigating(false);
      setLiveEvents([]);
      abortRef.current = null;
    }
  }

  async function handleApprove(actionId: string) {
    await api.approveAction(incidentId, actionId);
    await refresh();
  }

  async function handleReject(actionId: string) {
    await api.rejectAction(incidentId, actionId);
    await refresh();
  }

  if (incident === null) {
    return <div className="p-24 text-center text-slate-400">Loading…</div>;
  }

  const hypothesis = incident.hypotheses[incident.hypotheses.length - 1];
  const proposedActions = incident.tool_calls.filter(
    (tc) => tc.is_side_effecting && tc.status === "proposed",
  );
  const canInvestigate = incident.status !== "resolved" && incident.status !== "closed";

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{incident.title}</h1>
          {incident.description && <p className="mt-1 text-sm text-slate-500">{incident.description}</p>}
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge status={incident.status} />
            <span className="text-xs text-slate-400">
              Created {new Date(incident.created_at).toLocaleString()}
            </span>
          </div>
        </div>
        {canInvestigate && (
          <button
            onClick={handleInvestigate}
            disabled={investigating}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {investigating ? "Investigating…" : "Investigate"}
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Timeline</h2>
          <div className="mt-3">
            {investigating && liveEvents.length > 0 && (
              <ul className="mb-3 space-y-1.5 border-b border-dashed border-slate-200 pb-3 text-sm">
                {liveEvents.map((event, i) => (
                  <li
                    key={`${event.id}-${i}`}
                    className={`flex items-center gap-1.5 ${
                      event.kind === "error" ? "text-red-600" : "text-slate-600"
                    }`}
                  >
                    <span
                      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                        event.kind === "error" ? "bg-red-500" : "bg-slate-400"
                      }`}
                    />
                    {event.label}
                  </li>
                ))}
              </ul>
            )}
            <Timeline toolCalls={incident.tool_calls} />
          </div>
        </div>

        <div className="space-y-8 lg:col-span-2">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Hypothesis</h2>
            {hypothesis ? (
              <div className="mt-3 rounded-lg border border-slate-200 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase text-slate-400">
                    Confidence: {hypothesis.confidence}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-800">{hypothesis.summary}</p>
                {hypothesis.reasoning && (
                  <p className="mt-2 text-sm text-slate-500">{hypothesis.reasoning}</p>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                No hypothesis yet. Click Investigate to start.
              </p>
            )}
          </div>

          {proposedActions.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Proposed actions
              </h2>
              <div className="mt-3 space-y-3">
                {proposedActions.map((action) => (
                  <ProposedActionCard
                    key={action.id}
                    action={action}
                    onApprove={() => handleApprove(action.id)}
                    onReject={() => handleReject(action.id)}
                  />
                ))}
              </div>
            </div>
          )}

          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Evidence</h2>
            <div className="mt-3">
              <EvidencePanel evidence={incident.evidence} toolCalls={incident.tool_calls} />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function IncidentPage() {
  return (
    <ProtectedRoute>
      <InvestigationWorkspace />
    </ProtectedRoute>
  );
}
