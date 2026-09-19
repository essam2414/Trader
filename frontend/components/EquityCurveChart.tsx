// EquityCurveChart: Renders an area chart of portfolio value over time, with
// a subtle amber gradient fill under the line to match the dashboard's accent
// color. Shows an empty state when there's no snapshot history yet.

"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PortfolioSnapshot } from "../lib/types";

const AMBER = "#f59e0b";

export function EquityCurveChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  if (snapshots.length === 0) {
    return (
      <p className="text-sm text-zinc-500">Not enough history yet — check back after the next snapshot.</p>
    );
  }
  const data = snapshots.map((snapshot) => ({
    date: new Date(snapshot.takenAt).toLocaleDateString(),
    value: snapshot.totalValue,
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ left: -12, right: 12 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={AMBER} stopOpacity={0.25} />
            <stop offset="100%" stopColor={AMBER} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="date" stroke="#52525b" tick={{ fill: "#71717a", fontSize: 12 }} tickLine={false} />
        <YAxis
          domain={["auto", "auto"]}
          stroke="#52525b"
          tick={{ fill: "#71717a", fontSize: 12 }}
          tickLine={false}
          width={64}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #27272a",
            borderRadius: 6,
            fontSize: 12,
          }}
          labelStyle={{ color: "#a1a1aa" }}
          formatter={(value: number) => [value.toLocaleString(), "Value"]}
        />
        <Area type="monotone" dataKey="value" stroke={AMBER} strokeWidth={2} fill="url(#equityFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
