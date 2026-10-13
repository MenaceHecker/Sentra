"use client";

import { Fragment, useEffect, useState } from "react";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import * as api from "@/lib/api";
import type { AuditLogOut } from "@/lib/types";

function formatDetail(detailJson: string | null): string {
  if (!detailJson) return "";
  try {
    const parsed = JSON.parse(detailJson);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return detailJson;
  }
}

function AuditLogContent() {
  const [entries, setEntries] = useState<AuditLogOut[] | null>(null);
  const [actionFilter, setActionFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    api
      .getAuditLog(actionFilter ? { action: actionFilter } : undefined)
      .then(setEntries)
      .catch(() => setEntries([]));
  }, [actionFilter]);

  const actions = Array.from(new Set(entries?.map((e) => e.action) ?? []));

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="text-2xl font-semibold">Audit log</h1>
      <p className="mt-1 text-sm text-slate-500">
        Every tool call, hypothesis, and human decision across every
        investigation you own.
      </p>

      <div className="mt-6">
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All actions</option>
          {actions.map((action) => (
            <option key={action} value={action}>
              {action}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">Time</th>
              <th className="px-4 py-2">Actor</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">Incident</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {entries === null ? (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  Loading…
                </td>
              </tr>
            ) : entries.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  No audit entries yet.
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <Fragment key={entry.id}>
                  <tr
                    onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpanded(expanded === entry.id ? null : entry.id);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    aria-expanded={expanded === entry.id}
                    className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline focus:outline-2 focus:outline-offset-[-2px] focus:outline-slate-400"
                  >
                    <td className="whitespace-nowrap px-4 py-2 text-slate-500">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{entry.actor}</td>
                    <td className="px-4 py-2 font-medium text-slate-900">{entry.action}</td>
                    <td className="px-4 py-2 font-mono text-xs text-slate-400">
                      {entry.incident_id.slice(0, 8)}
                    </td>
                  </tr>
                  {expanded === entry.id && entry.detail_json && (
                    <tr>
                      <td colSpan={4} className="bg-slate-50 px-4 py-3">
                        <pre className="whitespace-pre-wrap text-xs text-slate-600">
                          {formatDetail(entry.detail_json)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

export default function AuditLogPage() {
  return (
    <ProtectedRoute>
      <AuditLogContent />
    </ProtectedRoute>
  );
}
