"use client";

import { useState } from "react";
import type { ToolCallOut } from "@/lib/types";

export function ProposedActionCard({
  action,
  onApprove,
  onReject,
}: {
  action: ToolCallOut;
  onApprove: () => Promise<void>;
  onReject: () => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(null);
  const input = JSON.parse(action.tool_input_json) as Record<string, unknown>;

  async function handle(kind: "approve" | "reject", fn: () => Promise<void>) {
    setSubmitting(kind);
    try {
      await fn();
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <div className="text-sm font-semibold text-amber-900">Proposed: {action.tool_name}</div>
      <dl className="mt-2 space-y-1 text-xs text-amber-800">
        {Object.entries(input).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt className="font-medium">{key}:</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-amber-700">
        This will not run until you approve it. Approving runs it immediately.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => handle("approve", onApprove)}
          disabled={submitting !== null}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting === "approve" ? "Approving…" : "Approve"}
        </button>
        <button
          onClick={() => handle("reject", onReject)}
          disabled={submitting !== null}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-white disabled:opacity-50"
        >
          {submitting === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
    </div>
  );
}
