// EquityCurveChart: Renders a line chart of portfolio value over time.
// Shows an empty state when there's no snapshot history yet.
// Displays total portfolio value on the Y-axis and dates on the X-axis.

"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PortfolioSnapshot } from "../lib/types";

export function EquityCurveChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  if (snapshots.length === 0) {
    return <p className="text-neutral-500">Not enough history yet — check back after the next snapshot.</p>;
  }
  const data = snapshots.map((snapshot) => ({
    date: new Date(snapshot.takenAt).toLocaleDateString(),
    value: snapshot.totalValue,
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <XAxis dataKey="date" />
        <YAxis domain={["auto", "auto"]} />
        <Tooltip />
        <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
