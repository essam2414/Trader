import type { SparklinePoint } from "./types";

export const SPARKLINE_WINDOW_MS = 24 * 60 * 60 * 1_000;
export const SPARKLINE_BUCKET_MS = 15 * 60 * 1_000;

export type LiveSparklinePrice = Pick<SparklinePoint, "timestamp" | "close">;

function validTimestamp(point: SparklinePoint): number | null {
  const timestamp = Date.parse(point.timestamp);
  return Number.isFinite(timestamp) && Number.isFinite(point.close) ? timestamp : null;
}

export function normaliseSparklinePoints(points: SparklinePoint[]): SparklinePoint[] {
  const byTimestamp = new Map<number, SparklinePoint>();
  for (const point of points) {
    const timestamp = validTimestamp(point);
    if (timestamp !== null) byTimestamp.set(timestamp, point);
  }
  return [...byTimestamp.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, point]) => point);
}

export function mergeLiveSparklinePrice(
  points: SparklinePoint[],
  update: LiveSparklinePrice,
  now = Date.now(),
): SparklinePoint[] {
  const timestamp = Date.parse(update.timestamp);
  if (!Number.isFinite(timestamp) || !Number.isFinite(update.close)) return normaliseSparklinePoints(points);

  const cutoff = now - SPARKLINE_WINDOW_MS;
  const bucket = Math.floor(timestamp / SPARKLINE_BUCKET_MS) * SPARKLINE_BUCKET_MS;
  const retained = normaliseSparklinePoints(points).filter((point) => Date.parse(point.timestamp) >= cutoff);
  const byTimestamp = new Map(retained.map((point) => [Date.parse(point.timestamp), point]));
  if (bucket >= cutoff && bucket <= now) {
    byTimestamp.set(bucket, { timestamp: new Date(bucket).toISOString(), close: update.close });
  }
  return [...byTimestamp.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, point]) => point);
}

export function createSparklinePath(
  points: SparklinePoint[],
  windowEnd: number,
  width = 104,
  height = 36,
  padding = 3,
): string | null {
  const windowStart = windowEnd - SPARKLINE_WINDOW_MS;
  const visible = normaliseSparklinePoints(points).filter((point) => {
    const timestamp = Date.parse(point.timestamp);
    return timestamp >= windowStart && timestamp <= windowEnd;
  });
  if (visible.length < 2) return null;

  const values = visible.map((point) => point.close);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const plotWidth = width - padding * 2;
  const plotHeight = height - padding * 2;
  const format = (value: number) => Number(value.toFixed(2));
  return visible
    .map((point, index) => {
      const x = format(padding + (index / (visible.length - 1)) * plotWidth);
      const y = format(padding + (1 - (point.close - minimum) / range) * plotHeight);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}
