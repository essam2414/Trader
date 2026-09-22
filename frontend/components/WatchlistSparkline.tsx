import type { SparklinePoint } from "../lib/types";
import { createSparklinePath, normaliseSparklinePoints } from "../lib/watchlistSparkline";

export type WatchlistTrend = "positive" | "negative" | "neutral";

interface WatchlistSparklineProps {
  points: SparklinePoint[];
  trend: WatchlistTrend;
}

export function WatchlistSparkline({ points, trend }: WatchlistSparklineProps) {
  const normalisedPoints = normaliseSparklinePoints(points);
  const latestTimestamp = Date.parse(normalisedPoints.at(-1)?.timestamp ?? "");
  const path = Number.isFinite(latestTimestamp)
    ? createSparklinePath(normalisedPoints, latestTimestamp)
    : null;
  if (!path) {
    return <span className="text-xs text-neutral-600">No session data</span>;
  }
  const lineColor = trend === "positive" ? "#42d95a" : trend === "negative" ? "#ff4e57" : "#78838a";

  return (
    <svg viewBox="0 0 104 36" role="img" aria-label="24-hour price direction" className="h-9 w-[104px]">
      <path
        d={path}
        fill="none"
        stroke={lineColor}
        strokeWidth="2.25"
        vectorEffect="non-scaling-stroke"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
