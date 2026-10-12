const STYLES: Record<string, string> = {
  investigating: "bg-blue-100 text-blue-800",
  hypothesis_ready: "bg-amber-100 text-amber-800",
  action_pending: "bg-orange-100 text-orange-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-slate-100 text-slate-600",
  proposed: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
  executed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  healthy: "bg-green-100 text-green-800",
  degraded: "bg-red-100 text-red-800",
  unknown: "bg-slate-100 text-slate-600",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STYLES[status] ?? "bg-slate-100 text-slate-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
