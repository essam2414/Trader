// EquityCurveChart: Renders an area chart of portfolio value over time, with
// a subtle monochrome gradient fill under the line to match the dashboard.
// color. Shows an empty state when there's no snapshot history yet.

"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PortfolioSnapshot } from "../lib/types";

const CHART_LINE = "#E5E5E5";

export function EquityCurveChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  if (snapshots.length === 0) {
    return (
      <p className="text-sm text-neutral-500">Not enough history yet — check back after the next snapshot.</p>
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
            <stop offset="0%" stopColor={CHART_LINE} stopOpacity={0.18} />
            <stop offset="100%" stopColor={CHART_LINE} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#262626" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="date" stroke="#525252" tick={{ fill: "#A3A3A3", fontSize: 12 }} tickLine={false} />
        <YAxis
          domain={["auto", "auto"]}
          stroke="#525252"
          tick={{ fill: "#A3A3A3", fontSize: 12 }}
          tickLine={false}
          width={64}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#171717",
            border: "1px solid #262626",
            borderRadius: 6,
            fontSize: 12,
          }}
          labelStyle={{ color: "#D4D4D4" }}
          formatter={(value) => [typeof value === "number" ? value.toLocaleString() : "-", "Value"]}
        />
        <Area type="monotone" dataKey="value" stroke={CHART_LINE} strokeWidth={2} fill="url(#equityFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
