"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCurrency } from "../lib/format";
import type { RealizedPnlEvent } from "../lib/types";

const WATCHLIST_BLUE = "#00AEEF";
const SINGLE_POINT_TIME_PADDING_MS = 60 * 60 * 1000;

type CumulativePnlPoint = {
  timestamp: number;
  value: number;
};

export function buildCumulativeRealizedPnlData(points: RealizedPnlEvent[]): CumulativePnlPoint[] {
  const chronologicalPoints = points
    .flatMap((point) => {
      const timestamp = Date.parse(point.takenAt);
      return Number.isFinite(timestamp) && Number.isFinite(point.realizedPnl)
        ? [{ timestamp, realizedPnl: point.realizedPnl }]
        : [];
    })
    .sort((left, right) => left.timestamp - right.timestamp);

  let cumulativePnl = 0;
  return chronologicalPoints.map((point) => {
    cumulativePnl += point.realizedPnl;
    return { timestamp: point.timestamp, value: cumulativePnl };
  });
}

function calculatePnlDomain(values: number[]): [number, number] {
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  if (low === high) return [-1, 1];

  const padding = (high - low) * 0.05;
  return [Math.floor(low - padding), Math.ceil(high + padding)];
}

function calculateTimeDomain(data: CumulativePnlPoint[]): [number, number] {
  const first = data[0].timestamp;
  const last = data[data.length - 1].timestamp;
  return first === last
    ? [first - SINGLE_POINT_TIME_PADDING_MS, last + SINGLE_POINT_TIME_PADDING_MS]
    : [first, last];
}

function formatTimeAxisLabel(timestamp: number, spanMs: number): string {
  const date = new Date(timestamp);
  if (spanMs <= 2 * 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: spanMs > 365 * 24 * 60 * 60 * 1000 ? "numeric" : undefined,
  });
}

export function CumulativeRealizedPnlChart({
  points,
  currency,
}: {
  points: RealizedPnlEvent[];
  currency: string;
}) {
  const data = buildCumulativeRealizedPnlData(points);
  if (data.length === 0) {
    return <p className="text-sm text-neutral-500">No realised P/L yet — closed trades will appear here.</p>;
  }

  const valueDomain = calculatePnlDomain(data.map((point) => point.value));
  const timeDomain = calculateTimeDomain(data);
  const timeSpan = timeDomain[1] - timeDomain[0];
  const axisCurrencyFormatter = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ left: -12, right: 12 }}>
        <defs>
          <linearGradient id="cumulativeRealizedPnlFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={WATCHLIST_BLUE} stopOpacity={0.22} />
            <stop offset="72%" stopColor={WATCHLIST_BLUE} stopOpacity={0.035} />
            <stop offset="100%" stopColor={WATCHLIST_BLUE} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#262626" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="timestamp"
          type="number"
          scale="time"
          domain={timeDomain}
          stroke="#525252"
          tick={{ fill: "#A3A3A3", fontSize: 12 }}
          tickFormatter={(timestamp) => formatTimeAxisLabel(timestamp, timeSpan)}
          tickLine={false}
          minTickGap={36}
        />
        <YAxis
          domain={valueDomain}
          stroke="#525252"
          tick={{ fill: "#A3A3A3", fontSize: 12 }}
          tickFormatter={(value) => axisCurrencyFormatter.format(value)}
          tickLine={false}
          width={84}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#171717",
            border: "1px solid #262626",
            borderRadius: 6,
            fontSize: 12,
          }}
          labelStyle={{ color: "#D4D4D4" }}
          labelFormatter={(timestamp) => new Date(Number(timestamp)).toLocaleString("en-GB")}
          formatter={(value) => [
            typeof value === "number" ? formatCurrency(value, currency) : "-",
            "Cumulative realised P/L",
          ]}
        />
        <Area
          type="linear"
          dataKey="value"
          stroke={WATCHLIST_BLUE}
          strokeWidth={2.5}
          fill="url(#cumulativeRealizedPnlFill)"
          dot={data.length === 1 ? { r: 4, fill: WATCHLIST_BLUE, strokeWidth: 0 } : false}
          activeDot={{ r: 4, fill: WATCHLIST_BLUE, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
