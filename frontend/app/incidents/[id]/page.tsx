"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ProposedActionCard } from "@/components/ProposedActionCard";
import * as api from "@/lib/api";
import type { IncidentDetailOut } from "@/lib/types";

function InvestigationWorkspace() {
  const params = useParams();
  const incidentId = params.id as string;

  const [incident, setIncident] = useState<IncidentDetailOut | null>(null);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIncident(await api.getIncident(incidentId));
    } catch {
      setIncident(null);
    }
  }, [incidentId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleInvestigate() {
    setInvestigating(true);
    setError(null);
    try {
      // investigateIncident already returns the full refreshed incident,
      // using it directly avoids a redundant GET and, more importantly, a
      // gap where "Investigating…" clears before the new hypothesis has
      // actually landed in state.
      const response = await api.investigateIncident(incidentId);
      setIncident(response.incident);
    } catch (err) {
      setError(
        err instanceof api.ApiError
          ? err.message
          : "Investigation failed. It may need an LLM_PROVIDER key configured on the backend.",
      );
    } finally {
      setInvestigating(false);
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
            {investigating ? "Investigating… (this can take up to 30s)" : "Investigate"}
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Timeline</h2>
          <div className="mt-3">
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
