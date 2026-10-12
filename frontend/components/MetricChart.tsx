"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MetricToolOutput } from "@/lib/types";

export function MetricChart({ output }: { output: MetricToolOutput }) {
  const data = output.points.map((p) => ({
    time: new Date(p.timestamp).toLocaleTimeString(),
    value: p.value,
  }));

  if (data.length === 0) {
    return <p className="text-sm text-slate-400">No data points in this window.</p>;
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={30} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip
            formatter={(value) => (typeof value === "number" ? value.toFixed(4) : String(value))}
          />
          <Line type="monotone" dataKey="value" stroke="#0f172a" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
