import { useState, type CSSProperties, type DragEvent, type PointerEvent } from "react";
import { useRouter } from "next/navigation";
import { formatWatchlistPrice } from "../lib/format";
import type { WatchlistEntry } from "../lib/types";
import { WatchlistSparkline, type WatchlistTrend } from "./WatchlistSparkline";

export type WatchlistMode = "default" | "move" | "delete";

interface WatchlistItemProps {
  entry: WatchlistEntry;
  mode: WatchlistMode;
  isDragging: boolean;
  isSavingOrder: boolean;
  onDragStart?: (event: DragEvent<HTMLDivElement>, assetId: string) => void;
  onDragOver?: (event: DragEvent<HTMLDivElement>, assetId: string) => void;
  onDrop?: (assetId: string) => void;
  onDragEnd?: () => void;
  onRemove: (assetId: string) => void;
  itemRef?: (element: HTMLDivElement | null) => void;
  onPointerDragStart?: (event: PointerEvent<HTMLDivElement>, assetId: string) => void;
  onPointerDragMove?: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerDragEnd?: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerDragCancel?: (event: PointerEvent<HTMLDivElement>) => void;
  dragStyle?: CSSProperties;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function displayName(name: string): string {
  return name
    .replaceAll(",", "")
    .replace(/\s+(?:Class|Series)\s+[A-Z0-9]+(?:\s+(?:Common|Ordinary|Preferred)\s+(?:Stock|Shares?))?$/i, "")
    .replace(/\s+(?:Common|Ordinary|Preferred)\s+(?:Stock|Shares?)$/i, "")
    .replace(/\s+(?:Incorporated|Inc\.?|Corporation|Corp\.?|Ltd\.?|PLC)$/i, "")
    .replace(/\s+Group Holdings?$/i, "")
    .replace(/\s+Holdings?(?:\s+Co(?:mpany)?\.?)?$/i, "")
    .trim() || name;
}

function trendFor(entry: WatchlistEntry): WatchlistTrend {
  const change = entry.quote.percentChange ?? entry.quote.dollarChange;
  if (change === null || change === 0) return "neutral";
  return change > 0 ? "positive" : "negative";
}

function chartTrendFor(entry: WatchlistEntry): WatchlistTrend {
  const points = entry.quote.sparkline;
  if (points.length >= 2) {
    const movement = points.at(-1)!.close - points[0].close;
    if (movement !== 0) return movement > 0 ? "positive" : "negative";
  }
  return trendFor(entry);
}

function CachedLogo({ name, logoUrl }: Pick<WatchlistEntry, "name" | "logoUrl">) {
  const [failedToLoad, setFailedToLoad] = useState(false);

  if (failedToLoad) return null;

  return (
    // This authenticated, cached image route cannot be fetched by Next's unauthenticated optimizer.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={`${name} logo`}
      className="absolute inset-0 h-full w-full bg-white object-contain p-1"
      src={logoUrl}
      onError={() => setFailedToLoad(true)}
    />
  );
}

export function StockLogo({ name, logoUrl, size = "default" }: Pick<WatchlistEntry, "name" | "logoUrl"> & { size?: "default" | "detail" }) {
  return (
    <span
      className={`relative flex shrink-0 items-center justify-center overflow-hidden bg-[#1b2227] text-xs font-bold tracking-tight text-neutral-100 ${size === "detail" ? "h-10 w-10 rounded-xl text-xs sm:h-12 sm:w-12" : "h-11 w-11 rounded-[14px]"}`}
      >
        <span aria-hidden="true">{initials(name)}</span>
      <CachedLogo key={logoUrl} name={name} logoUrl={logoUrl} />
    </span>
  );
}

export function WatchlistItem({
  entry,
  mode,
  isDragging,
  isSavingOrder,
  onRemove,
  itemRef,
  onPointerDragStart,
  onPointerDragMove,
  onPointerDragEnd,
  onPointerDragCancel,
  dragStyle,
}: WatchlistItemProps) {
  const router = useRouter();
  const trend = trendFor(entry);
  const chartTrend = chartTrendFor(entry);
  const percentChange = entry.quote.percentChange;
  const changeClass = trend === "positive" ? "text-[#32e64d]" : trend === "negative" ? "text-[#ff3b45]" : "text-[#8a9298]";
  const changeIndicator = trend === "positive" ? "↗" : trend === "negative" ? "↘" : "–";
  const delayedLabel = entry.quote.isDelayed || entry.quote.feed === "delayed_sip";
  const interactiveClass = mode === "move"
    ? "cursor-grab select-none touch-none active:cursor-grabbing"
    : mode === "delete"
      ? "cursor-pointer hover:bg-rose-400/[0.07] focus-visible:bg-rose-400/[0.07]"
      : "cursor-pointer hover:bg-neutral-800/40 focus-visible:bg-neutral-800/40";

  return (
    <div
      ref={itemRef}
      data-watchlist-entry={entry.assetId}
      draggable={false}
      onPointerDown={(event) => {
        if (mode !== "move" || isSavingOrder) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        onPointerDragStart?.(event, entry.assetId);
      }}
      onPointerMove={onPointerDragMove}
      onPointerUp={onPointerDragEnd}
      onPointerCancel={onPointerDragCancel}
      onClick={() => {
        if (mode === "delete") onRemove(entry.assetId);
        if (mode === "default") router.push(`/watchlist/${encodeURIComponent(entry.assetId)}`);
      }}
      onKeyDown={(event) => {
        if (mode === "delete" && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onRemove(entry.assetId);
        }
        if (mode === "default" && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          router.push(`/watchlist/${encodeURIComponent(entry.assetId)}`);
        }
      }}
      role={mode === "delete" ? "button" : mode === "default" ? "link" : undefined}
      aria-label={mode === "delete" ? `Remove ${entry.symbol}` : mode === "default" ? `View ${entry.symbol} chart` : undefined}
      tabIndex={mode === "delete" || mode === "default" ? 0 : undefined}
      style={dragStyle}
      className={`relative grid min-h-[68px] grid-cols-[44px_minmax(0,1fr)_104px_104px] items-center gap-x-3 rounded-xl px-2 py-2 transition-[background-color,opacity,box-shadow] duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-neutral-400 ${interactiveClass} ${isDragging ? "shadow-2xl shadow-black/70" : ""}`}
    >
      {mode === "move" && <span aria-hidden="true" className="absolute left-1 top-1/2 -translate-y-1/2 text-xs tracking-[-0.2em] text-neutral-600">⋮⋮</span>}
      <StockLogo name={entry.name} logoUrl={entry.logoUrl} />
      <div className="min-w-0">
        <p className="truncate text-[15px] font-semibold leading-tight text-[#f5f5f5] sm:text-[16px]">
          {displayName(entry.name)}
        </p>
        <p className="mt-0.5 truncate text-[13px] font-medium leading-none text-[#8a9298]">
          {entry.symbol}
        </p>
      </div>
      <div className="justify-self-end">
        <WatchlistSparkline points={entry.quote.sparkline} trend={chartTrend} />
      </div>
      <div className="min-w-0 text-right font-sans [font-variant-numeric:tabular-nums]">
        <p className="truncate text-[16px] font-semibold leading-tight text-[#f5f5f5] sm:text-[17px]">
          {entry.quote.price === null ? "—" : formatWatchlistPrice(entry.quote.price)}
        </p>
        <p className={`mt-0.5 truncate text-[13px] font-semibold leading-none sm:text-[14px] ${changeClass}`}>
          {percentChange === null ? "—" : `${changeIndicator} ${Math.abs(percentChange).toFixed(2)}%`}
        </p>
        {delayedLabel && (
          <p
            className="mt-1 truncate text-[10px] font-semibold uppercase tracking-wide text-amber-300"
            title="Consolidated SIP price delayed by approximately 15 minutes"
          >
            Delayed SIP · 15 min
          </p>
        )}
      </div>
    </div>
  );
}

export { displayName as conciseStockName };
