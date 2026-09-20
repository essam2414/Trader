import type { SparklinePoint } from "../lib/types";

export type WatchlistTrend = "positive" | "negative" | "neutral";

interface WatchlistSparklineProps {
  points: SparklinePoint[];
  trend: WatchlistTrend;
}

export function WatchlistSparkline({ points, trend }: WatchlistSparklineProps) {
  if (points.length < 2) {
    return <span className="text-xs text-neutral-600">No session data</span>;
  }
  const values = points.map((point) => point.close);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const coordinates = values.map((value, index) => ({
    x: 4 + (index / (values.length - 1)) * 102,
    y: 44 - ((value - minimum) / range) * 40,
  }));
  const accentStart = Math.max(1, Math.ceil((coordinates.length - 1) * 0.75));
  const mutedLine = coordinates.slice(0, accentStart + 1).map(({ x, y }) => `${x},${y}`).join(" ");
  // Include the preceding point so the coloured tail connects seamlessly to the muted history.
  const accentLine = coordinates.slice(accentStart - 1).map(({ x, y }) => `${x},${y}`).join(" ");
  const accentColor = trend === "positive" ? "#32e64d" : "#ff3b45";

  return (
    <svg viewBox="0 0 110 48" role="img" aria-label="Regular-session price direction" className="h-8 w-20">
      <polyline
        points={mutedLine}
        fill="none"
        stroke="#263238"
        strokeWidth="1.75"
        vectorEffect="non-scaling-stroke"
        strokeLinecap="round"
      />
      {trend !== "neutral" && accentLine.split(" ").length > 1 && (
        <polyline
          points={accentLine}
          fill="none"
          stroke={accentColor}
          strokeWidth="1.75"
          vectorEffect="non-scaling-stroke"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
