"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { conciseStockName, StockLogo } from "./WatchlistItem";
import type { ChartRange, StockChart, StockChartBar, WatchlistEntry, WatchlistPositionPrice } from "../lib/types";

const RANGES: ChartRange[] = ["1D", "1W", "1M", "3M", "1Y", "MAX"];

export interface ChartLiveState {
  bars: StockChartBar[];
  latestPrice: number | null;
}

interface StockPriceChartProps {
  assetId: string;
  range?: ChartRange;
  compact?: boolean;
  watchlistEntry?: WatchlistEntry;
  live?: ChartLiveState;
  purchasePriceOverride?: number | null;
}
type DisplayPoint = StockChartBar & { label: string };

function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatPriceNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

export function formatAxisPrice(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: 3 }).format(value);
}

function formatTimestamp(timestamp: string, range: ChartRange): string {
  const date = new Date(timestamp);
  return range === "1D"
    ? date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: range === "MAX" ? "2-digit" : undefined });
}

/** The transport retains provenance; the visual chart intentionally has one continuous series. */
export function mergeDisplayBars(chart: StockChart, liveBars: StockChartBar[] = []): DisplayPoint[] {
  const byTimestamp = new Map<string, StockChartBar>();
  for (const bar of chart.canonicalBars) byTimestamp.set(bar.startsAt, bar);
  for (const bar of chart.provisionalIexBars) byTimestamp.set(bar.startsAt, bar);
  for (const bar of liveBars) byTimestamp.set(bar.startsAt, bar);
  return [...byTimestamp.values()]
    .sort((left, right) => new Date(left.startsAt).getTime() - new Date(right.startsAt).getTime())
    .map((bar) => ({ ...bar, label: formatTimestamp(bar.startsAt, chart.range) }));
}

export function calculateRangeReturn(points: StockChartBar[], latestPrice: number | null): number | null {
  const first = points[0]?.open;
  const last = latestPrice ?? points.at(-1)?.close;
  return first && Number.isFinite(first) && last !== undefined && last !== null && Number.isFinite(last)
    ? ((last - first) / first) * 100
    : null;
}

function StockHeader({ entry, chart, compact }: { entry: WatchlistEntry | null; chart: StockChart | null; compact: boolean }) {
  const name = entry?.name ?? chart?.name;
  const symbol = entry?.symbol ?? chart?.symbol;
  if (!name || !symbol) return <div className="h-16" aria-hidden="true" />;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
      {entry ? <StockLogo name={entry.name} logoUrl={entry.logoUrl} size="detail" /> : <div className="h-10 w-10 rounded-xl bg-[#1b2227] sm:h-12 sm:w-12" />}
      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-wide text-neutral-400">{symbol} · {entry?.exchange ?? "US"}</p>
        {compact
          ? <h2 className="mt-0.5 truncate text-base font-medium leading-tight text-neutral-50" title={name}>{conciseStockName(name)}</h2>
          : <h1 className="mt-0.5 truncate text-lg font-medium leading-tight tracking-tight text-neutral-50 sm:text-xl" title={name}>{conciseStockName(name)}</h1>}
      </div>
    </div>
  );
}

function StockPriceSummary({ price, entry }: { price: number | null; entry: WatchlistEntry | null }) {
  const previousClose = entry?.quote.previousClose;
  const change = price !== null && previousClose !== null && previousClose !== undefined ? price - previousClose : entry?.quote.dollarChange;
  const percentage = change !== null && change !== undefined && previousClose ? (change / previousClose) * 100 : entry?.quote.percentChange;
  const direction = change === null || change === undefined || change === 0 ? "neutral" : change > 0 ? "positive" : "negative";
  const directionClass = direction === "positive" ? "text-[#32e64d]" : direction === "negative" ? "text-[#ff4b55]" : "text-neutral-500";
  const changeLabel = change !== null && change !== undefined && percentage !== null && percentage !== undefined
    ? `${direction === "positive" ? "↗ " : direction === "negative" ? "↘ " : ""}${formatPriceNumber(Math.abs(change))} (${Math.abs(percentage).toFixed(2)}%) today`
    : null;
  return (
    <div className="flex shrink-0 items-baseline gap-3 whitespace-nowrap sm:gap-5">
      <p data-testid="stock-current-price" className="font-sans text-2xl font-semibold leading-none tracking-tight text-white [font-variant-numeric:tabular-nums] lg:text-[2rem]">
        {price === null ? "—" : <><span className="mr-0.5 inline-block align-baseline text-[0.56em] tracking-normal">$</span>{formatPriceNumber(price)}</>}
      </p>
      {changeLabel && (
        <p className={`font-sans text-sm font-semibold leading-none [font-variant-numeric:tabular-nums] sm:text-base ${directionClass}`}>{changeLabel}</p>
      )}
    </div>
  );
}

function ChartRangeSelector({ range, onChange }: { range: ChartRange; onChange: (range: ChartRange) => void }) {
  return (
    <nav aria-label="Chart range" className="mt-5 flex w-full items-center justify-between gap-1 border-t border-white/[0.06] pt-5 sm:mt-6 sm:gap-3">
      {RANGES.map((value) => <button key={value} type="button" aria-pressed={range === value} onClick={() => onChange(value)} className={`min-w-11 rounded-full px-3 py-2 text-xs font-semibold transition sm:min-w-14 sm:px-4 sm:text-sm ${range === value ? "bg-[#292929] text-white" : "text-neutral-500 hover:text-neutral-200"}`}>{value}</button>)}
    </nav>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: DisplayPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="rounded-md bg-[#171717]/95 px-2.5 py-2 text-xs shadow-lg shadow-black/30"><p className="text-neutral-400">{point.label}</p><p className="mt-0.5 font-medium text-white [font-variant-numeric:tabular-nums]">{formatPrice(point.close)}</p></div>;
}

function upsertLiveBar(bars: StockChartBar[], next: StockChartBar): StockChartBar[] {
  const index = bars.findIndex((bar) => bar.startsAt === next.startsAt);
  if (index === -1) return [...bars, next].sort((left, right) => left.startsAt.localeCompare(right.startsAt));
  const updated = [...bars];
  updated[index] = next;
  return updated;
}

export function StockPriceChart({ assetId, range: controlledRange, compact = false, watchlistEntry, live, purchasePriceOverride }: StockPriceChartProps) {
  const [localRange, setLocalRange] = useState<ChartRange>("1D");
  const range = controlledRange ?? localRange;
  const gradientId = useId().replaceAll(":", "");
  const [chart, setChart] = useState<StockChart | null>(null);
  const [entry, setEntry] = useState<WatchlistEntry | null>(null);
  const [positionPrice, setPositionPrice] = useState<{ assetId: string; price: number | null } | null>(null);
  const [liveBars, setLiveBars] = useState<StockChartBar[]>([]);
  const [latestPrice, setLatestPrice] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (watchlistEntry) return;
    const controller = new AbortController();
    fetch("/api/watchlist", { signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<WatchlistEntry[]> : Promise.reject(new Error("Watchlist unavailable")))
      .then((entries) => setEntry(entries.find((item) => item.assetId === assetId) ?? null))
      .catch(() => undefined);
    return () => controller.abort();
  }, [assetId, watchlistEntry]);

  useEffect(() => {
    if (purchasePriceOverride !== undefined) return;
    const controller = new AbortController();
    fetch(`/api/watchlist/${encodeURIComponent(assetId)}/position`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<WatchlistPositionPrice> : Promise.reject(new Error("Position unavailable")))
      .then((position) => setPositionPrice({ assetId, price: typeof position.purchasePrice === "number" && Number.isFinite(position.purchasePrice) ? position.purchasePrice : null }))
      .catch(() => undefined);
    return () => controller.abort();
  }, [assetId, purchasePriceOverride]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/watchlist/${encodeURIComponent(assetId)}/chart?range=${range}`, { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Price history unavailable."); return response.json() as Promise<StockChart>; })
      .then((result) => { setChart(result); setError(null); })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Price history unavailable."); })
    return () => controller.abort();
  }, [assetId, range]);

  useEffect(() => {
    if (compact || typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/watchlist/${encodeURIComponent(assetId)}/chart/stream`);
    source.addEventListener("live_snapshot", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as { bars?: StockChartBar[]; latestTrade?: { price: number } };
        setLiveBars(payload.bars ?? []);
        setLatestPrice(payload.latestTrade?.price ?? null);
      } catch { /* A later stream event repairs malformed transient data. */ }
    });
    source.addEventListener("bar", (event) => {
      try {
        const bar = JSON.parse((event as MessageEvent<string>).data) as StockChartBar;
        setLiveBars((current) => upsertLiveBar(current, bar));
        setLatestPrice(bar.close);
      } catch { /* Ignore malformed transient provider data. */ }
    });
    source.addEventListener("trade", (event) => {
      try { setLatestPrice((JSON.parse((event as MessageEvent<string>).data) as { price: number }).price); } catch { /* Ignore malformed transient provider data. */ }
    });
    return () => source.close();
  }, [assetId, compact]);

  const currentEntry = watchlistEntry ?? entry;
  const currentLivePrice = compact ? live?.latestPrice ?? null : latestPrice;
  const data = useMemo(
    () => chart ? mergeDisplayBars(chart, compact ? live?.bars ?? [] : liveBars) : [],
    [chart, compact, live?.bars, liveBars],
  );
  const purchasePrice = purchasePriceOverride !== undefined
    ? purchasePriceOverride
    : positionPrice?.assetId === assetId ? positionPrice.price : null;
  const isLoading = chart?.range !== range && error === null;
  const lastClose = data.at(-1)?.close ?? currentEntry?.quote.price ?? null;
  const displayedPrice = currentLivePrice ?? currentEntry?.quote.price ?? lastClose;
  const rangeReturn = chart?.range === range ? calculateRangeReturn(data, displayedPrice) : null;
  const plotData = useMemo(() => {
    const lastIndex = data.length - 1;
    return data.map((point, index) => ({
      ...point,
      close: displayedPrice !== null && index === lastIndex ? displayedPrice : point.close,
    }));
  }, [data, displayedPrice]);
  const yDomain = useMemo<[number, number]>(() => {
    const values = plotData.map((point) => point.close);
    if (displayedPrice !== null) values.push(displayedPrice);
    if (purchasePrice !== null) values.push(purchasePrice);
    if (values.length === 0) return [0, 1];
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const paddingRatio = range === "MAX" ? 0.22 : 0.14;
    const padding = Math.max((maximum - minimum) * paddingRatio, Math.abs(maximum) * 0.004, 0.01);
    return [minimum - padding, maximum + padding];
  }, [displayedPrice, plotData, purchasePrice, range]);
  const purchaseLevelPercent = purchasePrice === null
    ? null
    : ((yDomain[1] - purchasePrice) / (yDomain[1] - yDomain[0])) * 100;
  const axisWidth = compact ? 48 : 72;

  return (
    <section aria-label={compact ? `${currentEntry?.symbol ?? chart?.symbol ?? "Stock"} price chart` : "Stock price chart"} className="stock-price-chart w-full font-sans">
      <div className="w-full">
        <div role="group" aria-label="Stock overview" className={compact ? "flex min-w-0 items-center justify-between gap-2" : "flex min-w-0 flex-nowrap items-center justify-between gap-4 sm:gap-6"}>
          <StockHeader entry={currentEntry} chart={chart} compact={compact} />
          {!compact && <StockPriceSummary price={displayedPrice} entry={currentEntry} />}
        </div>
        {compact && <div className="mt-5 flex items-baseline justify-between gap-2 font-sans [font-variant-numeric:tabular-nums]">
          <p className="truncate text-xl font-semibold text-white">{displayedPrice === null ? "—" : formatPrice(displayedPrice)}</p>
          <p aria-label="Selected range return" title="Change from the first chart bar open to the latest displayed price" className={`shrink-0 text-sm font-semibold ${rangeReturn === null ? "text-neutral-500" : rangeReturn > 0 ? "text-[#32e64d]" : rangeReturn < 0 ? "text-[#ff4b55]" : "text-neutral-400"}`}>
            {rangeReturn === null ? "—" : `${rangeReturn > 0 ? "+" : ""}${rangeReturn.toFixed(2)}%`}
          </p>
        </div>}
        {!compact && <div aria-hidden="true" className="mt-6 -mx-5 w-[calc(100%+2.5rem)] border-t border-neutral-800/80 sm:-mx-8 sm:w-[calc(100%+4rem)] lg:-mx-10 lg:w-[calc(100%+5rem)]" />}
        <div className={compact ? "" : "lg:grid lg:grid-cols-[55fr_45fr]"}>
          <div className={compact ? "min-w-0" : "min-w-0 lg:pr-8"}>
            <div data-testid="stock-chart-plot" className={compact ? "relative -ml-2 -mr-3 mt-4 h-[220px] w-[calc(100%+1.25rem)]" : "relative mt-5 h-[280px] w-full sm:mt-6 sm:h-[340px] lg:h-[380px]"}>
            {error ? <div className="flex h-full items-center justify-center text-sm text-neutral-500">Price history unavailable.</div> : isLoading ? <div className="flex h-full items-center justify-center text-sm text-neutral-600">Loading price history…</div> : plotData.length === 0 ? <div className="flex h-full items-center justify-center text-sm text-neutral-500">Price history unavailable.</div> : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={plotData} margin={{ top: 20, right: 0, bottom: 4, left: 0 }} accessibilityLayer={false}>
                  <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#00AEEF" stopOpacity={0.22} /><stop offset="72%" stopColor="#00AEEF" stopOpacity={0.035} /><stop offset="100%" stopColor="#00AEEF" stopOpacity={0} /></linearGradient></defs>
                  <YAxis domain={yDomain} orientation="right" axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 11, fontFamily: "var(--font-sans)" }} tickFormatter={formatAxisPrice} tickCount={8} width={axisWidth} tickMargin={compact ? 4 : 18} />
                  <Tooltip content={<ChartTooltip />} cursor={false} wrapperStyle={{ outline: "none" }} />
                  <Area type="linear" dataKey="close" stroke="#00AEEF" strokeWidth={2.5} fill={`url(#${gradientId})`} dot={false} activeDot={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
            {purchaseLevelPercent !== null && purchasePrice !== null && (
              <div aria-hidden="false" className="pointer-events-none absolute top-5 right-0 bottom-1 left-0 z-10" style={{ right: axisWidth }}>
                <div
                  data-testid="purchase-price-line"
                  role="img"
                  aria-label={`Average purchase price ${formatPrice(purchasePrice)}`}
                  className="absolute right-0 left-0 border-t border-dashed border-[#737373]"
                  style={{ top: `${purchaseLevelPercent}%` }}
                >
                  <span aria-hidden="true" className="absolute right-1 bottom-1 rounded bg-[#171717]/85 px-1 text-[10px] text-neutral-400">Avg {formatPrice(purchasePrice)}</span>
                </div>
              </div>
            )}
          </div>
            {!compact && <ChartRangeSelector range={range} onChange={(nextRange) => { setError(null); setLocalRange(nextRange); }} />}
          </div>
          {!compact && <aside aria-label="Stock analysis" className="mt-8 min-h-40 border-t border-neutral-800/80 pt-6 lg:mt-0 lg:min-h-[380px] lg:border-t-0 lg:border-l lg:pl-10 lg:pt-6">
            <h2 className="text-sm font-semibold text-neutral-200">Analysis</h2>
            <p className="mt-3 text-sm leading-6 text-neutral-500">Stock analysis will appear here.</p>
          </aside>}
        </div>
      </div>
    </section>
  );
}
