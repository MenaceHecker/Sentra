"use client";

import { useState } from "react";
import { MetricChart } from "./MetricChart";
import type {
  DeployToolOutput,
  EvidenceOut,
  LogToolOutput,
  RunbookToolOutput,
  ToolCallOut,
} from "@/lib/types";

function parseOutput<T>(toolCall: ToolCallOut | undefined): T | null {
  if (!toolCall?.tool_output_json) return null;
  try {
    return JSON.parse(toolCall.tool_output_json) as T;
  } catch {
    return null;
  }
}

function EvidenceDetail({ evidence, toolCall }: { evidence: EvidenceOut; toolCall?: ToolCallOut }) {
  if (evidence.evidence_type === "log") {
    const output = parseOutput<LogToolOutput>(toolCall);
    if (!output) return <p className="text-sm text-slate-400">No log data available.</p>;
    return (
      <ul className="max-h-64 space-y-1 overflow-y-auto font-mono text-xs">
        {output.logs.map((log, i) => (
          <li key={i} className={log.level === "ERROR" ? "text-red-700" : "text-slate-600"}>
            [{new Date(log.timestamp).toLocaleTimeString()}] {log.level}: {log.message}
          </li>
        ))}
      </ul>
    );
  }

  if (evidence.evidence_type === "metric") {
    const output = parseOutput<{ service: string; metric_name: string; count: number; points: { timestamp: string; value: number }[] }>(
      toolCall,
    );
    if (!output) return <p className="text-sm text-slate-400">No metric data available.</p>;
    return <MetricChart output={output} />;
  }

  if (evidence.evidence_type === "deploy") {
    const output = parseOutput<DeployToolOutput>(toolCall);
    if (!output) return <p className="text-sm text-slate-400">No deploy data available.</p>;
    return (
      <ul className="space-y-2 text-xs">
        {output.deploys.map((d) => (
          <li key={d.sha} className="rounded border border-slate-200 p-2">
            <div className="font-mono text-slate-700">{d.sha}</div>
            <div className="text-slate-600">{d.message}</div>
            <div className="text-slate-400">
              {new Date(d.deployed_at).toLocaleString()} by {d.deployed_by}
            </div>
          </li>
        ))}
      </ul>
    );
  }

  if (evidence.evidence_type === "runbook") {
    const output = parseOutput<RunbookToolOutput>(toolCall);
    if (!output) return <p className="text-sm text-slate-400">No runbook data available.</p>;
    return (
      <div className="space-y-3 text-xs">
        {output.results.map((r, i) => (
          <div key={i} className="rounded border border-slate-200 p-2">
            <div className="font-medium text-slate-700">
              {r.document_title} (lines {r.start_line}-{r.end_line})
            </div>
            <pre className="mt-1 whitespace-pre-wrap text-slate-600">{r.content}</pre>
          </div>
        ))}
      </div>
    );
  }

  return null;
}

export function EvidencePanel({ evidence, toolCalls }: { evidence: EvidenceOut[]; toolCalls: ToolCallOut[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (evidence.length === 0) {
    return <p className="text-sm text-slate-400">No evidence gathered yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {evidence.map((item) => {
        const toolCall = toolCalls.find((tc) => tc.id === item.tool_call_id);
        const expanded = expandedId === item.id;
        return (
          <li key={item.id} className="rounded-lg border border-slate-200">
            <button
              onClick={() => setExpandedId(expanded ? null : item.id)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
            >
              <span>
                <span className="mr-2 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-500">
                  {item.evidence_type}
                </span>
                {item.summary}
              </span>
              <span className="text-slate-400">{expanded ? "−" : "+"}</span>
            </button>
            {expanded && (
              <div className="border-t border-slate-100 px-3 py-3">
                <EvidenceDetail evidence={item} toolCall={toolCall} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
