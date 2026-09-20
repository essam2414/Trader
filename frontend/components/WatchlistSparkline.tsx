import type { SparklinePoint } from "../lib/types";

export function WatchlistSparkline({ points, positive }: { points: SparklinePoint[]; positive: boolean }) {
  if (points.length < 2) {
    return <span className="text-xs text-neutral-600">No session data</span>;
  }
  const values = points.map((point) => point.close);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const line = values
    .map((value, index) => `${(index / (values.length - 1)) * 100},${28 - ((value - minimum) / range) * 24}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 28" role="img" aria-label="Regular-session price direction" className="h-8 w-28">
      <polyline
        points={line}
        fill="none"
        stroke={positive ? "#34d399" : "#fb7185"}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
