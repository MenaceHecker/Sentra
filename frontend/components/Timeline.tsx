import { StatusBadge } from "./StatusBadge";
import type { ToolCallOut } from "@/lib/types";

export function Timeline({ toolCalls }: { toolCalls: ToolCallOut[] }) {
  if (toolCalls.length === 0) {
    return <p className="text-sm text-slate-400">No tool calls yet. Run an investigation to start.</p>;
  }

  const sorted = [...toolCalls].sort(
    (a, b) => new Date(a.requested_at).getTime() - new Date(b.requested_at).getTime(),
  );

  return (
    <ol className="space-y-3">
      {sorted.map((call) => (
        <li key={call.id} className="flex items-start gap-3 text-sm">
          <div className="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-slate-300" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-slate-900">{call.tool_name}</span>
              <StatusBadge status={call.status} />
            </div>
            <div className="text-xs text-slate-400">
              {new Date(call.requested_at).toLocaleTimeString()}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
