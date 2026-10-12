"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { StatusBadge } from "@/components/StatusBadge";
import * as api from "@/lib/api";
import type { IncidentOut, ScenarioOut } from "@/lib/types";

function DashboardContent() {
  const router = useRouter();
  const [incidents, setIncidents] = useState<IncidentOut[] | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioOut[] | null>(null);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.listIncidents().then(setIncidents).catch(() => setIncidents([]));
  }, []);

  useEffect(() => {
    refresh();
    api
      .listScenarios()
      .then((list) => {
        setScenarios(list);
        if (list.length > 0) setSelectedScenario(list[0].id);
      })
      .catch(() => setScenarios([])); // simulated system may just not be reachable
  }, [refresh]);

  async function handleTrigger() {
    const scenario = scenarios?.find((s) => s.id === selectedScenario);
    if (!scenario) return;

    setTriggering(true);
    setError(null);
    try {
      await api.injectScenario(scenario.id);
      const incident = await api.createIncident(
        scenario.title,
        `Seeded scenario "${scenario.id}" on ${scenario.service}. ${scenario.description}`,
      );
      router.push(`/incidents/${incident.id}`);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Could not trigger the scenario.");
    } finally {
      setTriggering(false);
    }
  }

  async function handleBlankIncident() {
    const incident = await api.createIncident("New incident");
    router.push(`/incidents/${incident.id}`);
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <section className="mt-8 rounded-lg border border-slate-200 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Trigger a seeded incident
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Injects a real failure into the simulated system, then opens an
          incident for it.
        </p>
        {scenarios === null ? (
          <p className="mt-3 text-sm text-slate-400">Loading scenarios…</p>
        ) : scenarios.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">
            No scenarios available right now. Is the simulated system running?
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <select
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} ({s.service})
                </option>
              ))}
            </select>
            <button
              onClick={handleTrigger}
              disabled={triggering}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {triggering ? "Triggering…" : "Trigger incident"}
            </button>
            <button
              onClick={handleBlankIncident}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              Or start a blank incident
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Your investigations
        </h2>
        {incidents === null ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : incidents.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">
            No incidents yet, trigger one above to see Sentra investigate.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-200 rounded-lg border border-slate-200">
            {incidents.map((incident) => (
              <li key={incident.id}>
                <button
                  onClick={() => router.push(`/incidents/${incident.id}`)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
                >
                  <div>
                    <div className="text-sm font-medium text-slate-900">{incident.title}</div>
                    <div className="text-xs text-slate-400">
                      {new Date(incident.created_at).toLocaleString()}
                    </div>
                  </div>
                  <StatusBadge status={incident.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
