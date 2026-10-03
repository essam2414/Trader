"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type DragEvent } from "react";
import { StockPriceChart, type ChartLiveState } from "./StockPriceChart";
import { conciseStockName } from "./WatchlistItem";
import type { StockChartBar, TrendRank, WatchlistEntry, WatchlistPositionPrice } from "../lib/types";
import { TREND_RANGES, useTrendsPreferences } from "../lib/useTrendsPreferences";

export { readSavedTrends } from "../lib/useTrendsPreferences";

type LiveSnapshot = { symbol: string; bars?: StockChartBar[]; latestTrade?: { price: number } };
type LiveBar = StockChartBar & { symbol: string };

export function moveSelectedAsset(ids: string[], assetId: string, targetId: string): string[] {
  const from = ids.indexOf(assetId);
  const to = ids.indexOf(targetId);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = [...ids];
  next.splice(from, 1);
  next.splice(to, 0, assetId);
  return next;
}

function upsertBar(bars: StockChartBar[], next: StockChartBar): StockChartBar[] {
  return [...bars.filter((bar) => bar.startsAt !== next.startsAt), next]
    .sort((left, right) => left.startsAt.localeCompare(right.startsAt));
}

export function TrendsPage() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const { selectedIds, setSelectedIds, range, setRange, hydrated, loadError, saveError, saving, retryLoad, retrySave } = useTrendsPreferences();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [mode, setMode] = useState<"default" | "reorder" | "remove">("default");
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [liveBySymbol, setLiveBySymbol] = useState<Record<string, ChartLiveState>>({});
  const [purchasePrices, setPurchasePrices] = useState<Record<string, number | null>>({});
  const [ranking, setRanking] = useState(false);
  const [trendRanks, setTrendRanks] = useState<TrendRank[] | null>(null);
  const [trendMessage, setTrendMessage] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const selectedIdsRef = useRef(selectedIds);
  const tileRefs = useRef(new Map<string, HTMLDivElement>());
  const previousRects = useRef(new Map<string, DOMRect>());
  const animations = useRef(new Map<string, Animation>());

  useEffect(() => {
    selectedIdsRef.current = selectedIds;
  }, [selectedIds]);

  const loadWatchlist = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/watchlist", { cache: "no-store", signal });
      if (!response.ok) throw new Error("Watchlist unavailable");
      const list = await response.json() as WatchlistEntry[];
      if (signal?.aborted) return;
      setEntries(list);
      const available = new Set(list.map((entry) => entry.assetId));
      setSelectedIds((current) => current.filter((id) => available.has(id)));
      setStatus("ready");
    } catch {
      if (!signal?.aborted) setStatus("error");
    }
  }, [setSelectedIds]);

  const loadPurchasePrices = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/watchlist/positions", { cache: "no-store", signal });
      if (!response.ok) return;
      const levels = await response.json() as Record<string, WatchlistPositionPrice>;
      if (!signal?.aborted) setPurchasePrices(Object.fromEntries(
        Object.entries(levels).map(([assetId, level]) => [assetId, level.purchasePrice]),
      ));
    } catch { /* Charts remain available when position data is unavailable. */ }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadWatchlist(controller.signal);
      void loadPurchasePrices(controller.signal);
    }, 0);
    const refreshOnReturn = () => {
      if (document.visibilityState === "visible") {
        void loadWatchlist(controller.signal);
        void loadPurchasePrices(controller.signal);
      }
    };
    document.addEventListener("visibilitychange", refreshOnReturn);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", refreshOnReturn);
    };
  }, [hydrated, loadPurchasePrices, loadWatchlist]);

  useEffect(() => {
    if (!pickerOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setPickerOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPickerOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [pickerOpen]);

  const byId = new Map(entries.map((entry) => [entry.assetId, entry]));
  const selectedEntries = selectedIds.map((id) => byId.get(id)).filter((entry): entry is WatchlistEntry => !!entry);
  const rankById = new Map(trendRanks?.map((item) => [item.assetId, item]) ?? []);
  const orderKey = selectedEntries.map((entry) => entry.assetId).join(",");
  const selectedKey = selectedEntries.map((entry) => entry.assetId).sort().join(",");
  const symbolsKey = selectedEntries.map((entry) => entry.symbol).sort().join(",");

  useEffect(() => {
    if (!symbolsKey || !selectedKey || typeof EventSource === "undefined") return;
    const allowed = new Set(symbolsKey.split(","));
    const source = new EventSource(`/api/watchlist/charts/stream?assetIds=${encodeURIComponent(selectedKey)}`);
    source.addEventListener("live_snapshot", (event) => {
      try {
        const snapshot = JSON.parse((event as MessageEvent<string>).data) as LiveSnapshot;
        if (!allowed.has(snapshot.symbol)) return;
        setLiveBySymbol((current) => ({ ...current, [snapshot.symbol]: {
          bars: Array.isArray(snapshot.bars) ? snapshot.bars : [],
          latestPrice: typeof snapshot.latestTrade?.price === "number" ? snapshot.latestTrade.price : null,
        } }));
      } catch { /* The next stream event can repair malformed transient data. */ }
    });
    source.addEventListener("bar", (event) => {
      try {
        const bar = JSON.parse((event as MessageEvent<string>).data) as LiveBar;
        if (!allowed.has(bar.symbol)) return;
        setLiveBySymbol((current) => ({ ...current, [bar.symbol]: {
          bars: upsertBar(current[bar.symbol]?.bars ?? [], bar), latestPrice: bar.close,
        } }));
      } catch { /* Ignore malformed transient data. */ }
    });
    source.addEventListener("trade", (event) => {
      try {
        const trade = JSON.parse((event as MessageEvent<string>).data) as { symbol: string; price: number };
        if (!allowed.has(trade.symbol) || !Number.isFinite(trade.price)) return;
        setLiveBySymbol((current) => ({ ...current, [trade.symbol]: {
          bars: current[trade.symbol]?.bars ?? [], latestPrice: trade.price,
        } }));
      } catch { /* Ignore malformed transient data. */ }
    });
    return () => source.close();
  }, [selectedKey, symbolsKey]);

  useLayoutEffect(() => {
    const nextRects = new Map<string, DOMRect>();
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    for (const assetId of orderKey ? orderKey.split(",") : []) {
      const element = tileRefs.current.get(assetId);
      if (!element) continue;
      const current = element.getBoundingClientRect();
      const previous = previousRects.current.get(assetId);
      if (previous && !reduceMotion && typeof element.animate === "function") {
        const dx = previous.left - current.left;
        const dy = previous.top - current.top;
        if (dx || dy) {
          animations.current.get(assetId)?.cancel();
          animations.current.set(assetId, element.animate(
            [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }],
            { duration: 240, easing: "cubic-bezier(0.2, 0, 0, 1)" },
          ));
        }
      }
      nextRects.set(assetId, current);
    }
    previousRects.current = nextRects;
  }, [orderKey]);

  function toggleSelected(assetId: string) {
    if (ranking) return;
    setTrendRanks(null);
    setTrendMessage(null);
    setSelectedIds((current) => current.includes(assetId)
      ? current.filter((id) => id !== assetId)
      : [...current, assetId]);
  }

  function moveByKeyboard(assetId: string, delta: number) {
    setTrendRanks(null);
    setTrendMessage(null);
    setSelectedIds((current) => {
      const index = current.indexOf(assetId);
      if (index < 0) return current;
      const target = Math.max(0, Math.min(current.length - 1, index + delta));
      if (target === index) return current;
      const next = [...current];
      next.splice(index, 1);
      next.splice(target, 0, assetId);
      return next;
    });
  }

  function dragOver(event: DragEvent<HTMLDivElement>, targetId: string) {
    if (!draggedId || draggedId === targetId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setTrendRanks(null);
    setTrendMessage(null);
    setSelectedIds((current) => moveSelectedAsset(current, draggedId, targetId));
  }

  async function rankSelected() {
    if (ranking || selectedIds.length < 2) return;
    const requested = [...selectedIds];
    setRanking(true);
    setMode("default");
    setPickerOpen(false);
    setTrendError(null);
    setTrendMessage(null);
    try {
      const response = await fetch(`/api/watchlist/trends?assetIds=${encodeURIComponent(requested.join(","))}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Trend data is unavailable. Your chart order was kept.");
      const results = await response.json() as TrendRank[];
      if (!Array.isArray(results) || results.length !== requested.length
        || results.some((result) => !requested.includes(result.assetId))
        || new Set(results.map((result) => result.assetId)).size !== requested.length) {
        throw new Error("Trend data was incomplete. Your chart order was kept.");
      }
      const scored = results.filter((result) => result.status === "ready");
      if (scored.length === 0) throw new Error("There is not enough recent price history to rank these stocks.");
      if ([...selectedIdsRef.current].sort().join(",") !== [...requested].sort().join(",")) {
        throw new Error("The selected stocks changed during ranking. Your chart order was kept.");
      }
      setSelectedIds(results.map((result) => result.assetId));
      setTrendRanks(results);
      const missing = results.length - scored.length;
      setTrendMessage(`Ranked ${scored.length} stock${scored.length === 1 ? "" : "s"} using recent direction and one-month recovery.${missing ? ` ${missing} without enough data kept at the end.` : ""}`);
    } catch (error) {
      setTrendError(error instanceof Error ? error.message : "Trend data is unavailable. Your chart order was kept.");
    } finally {
      setRanking(false);
    }
  }

  return (
    <main className="min-h-screen w-full font-sans">
      <div className="mb-7 border-b border-neutral-800">
        <div className="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-4 px-6 pb-5 pt-8 xl:px-8">
          <div className="flex flex-wrap items-center gap-2">
            <nav aria-label="Trends chart range" className="flex flex-wrap items-center gap-1 rounded-xl border border-neutral-800 bg-neutral-900/50 p-1">
              {TREND_RANGES.map((option) => <button key={option} type="button" disabled={!hydrated || status !== "ready"} aria-pressed={range === option} onClick={() => setRange(option)} className={`min-w-12 rounded-lg px-3 py-2 text-sm font-semibold transition-colors disabled:opacity-40 ${range === option ? "bg-neutral-200 text-neutral-950" : "text-neutral-400 hover:bg-neutral-800 hover:text-white"}`}>{option}</button>)}
            </nav>
            <button type="button" onClick={() => void rankSelected()} disabled={ranking || selectedEntries.length < 2 || status !== "ready"} className="rounded-lg border border-sky-500/50 px-3 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/10 disabled:cursor-not-allowed disabled:opacity-40">{ranking ? "Ranking…" : "Trend"}</button>
          </div>
          <div className="flex items-center gap-2">
            <div ref={pickerRef} className="relative">
              <button type="button" aria-expanded={pickerOpen} aria-controls="trends-stock-picker" onClick={() => setPickerOpen((open) => !open)} disabled={ranking || !hydrated || status !== "ready"} className="rounded-lg border border-neutral-700 px-3 py-2 text-sm font-medium text-neutral-100 transition hover:bg-neutral-800 disabled:opacity-40">Add stocks</button>
              {pickerOpen && <div id="trends-stock-picker" className="absolute right-0 top-full z-30 mt-2 max-h-80 w-72 overflow-y-auto rounded-xl border border-neutral-700 bg-[#171717] p-2 shadow-xl shadow-black/50">
                <p className="px-2 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500">Watchlist stocks</p>
                {entries.length === 0 ? <p className="px-2 py-3 text-sm text-neutral-400">Your watchlist is empty.</p> : entries.map((entry) => <label key={entry.assetId} className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-neutral-800">
                  <input type="checkbox" checked={selectedIds.includes(entry.assetId)} onChange={() => toggleSelected(entry.assetId)} className="accent-[#00AEEF]" />
                  <span className="font-semibold text-neutral-100">{entry.symbol}</span><span className="truncate text-neutral-400">{conciseStockName(entry.name)}</span>
                </label>)}
              </div>}
            </div>
            <button type="button" aria-pressed={mode === "reorder"} onClick={() => setMode(mode === "reorder" ? "default" : "reorder")} disabled={ranking || (selectedEntries.length < 2 && mode !== "reorder")} className={`rounded-lg border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${mode === "reorder" ? "border-neutral-300 bg-neutral-200 text-neutral-950" : "border-neutral-700 text-neutral-200 hover:bg-neutral-800"}`}>{mode === "reorder" ? "Done" : "Reorder"}</button>
            <button type="button" aria-pressed={mode === "remove"} onClick={() => setMode(mode === "remove" ? "default" : "remove")} disabled={ranking || (selectedEntries.length === 0 && mode !== "remove")} className={`rounded-lg border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${mode === "remove" ? "border-rose-300 bg-rose-300 text-neutral-950" : "border-neutral-700 text-rose-300 hover:bg-rose-400/10"}`}>{mode === "remove" ? "Done" : "Remove"}</button>
          </div>
        </div>
      </div>
      <div className="mx-auto w-full max-w-[1440px] px-6 pb-8 xl:px-8">
      {loadError && <div role="alert" className="mb-5 flex items-center gap-4 rounded-xl border border-amber-900/50 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">{loadError} <button type="button" onClick={retryLoad} className="underline">Retry</button></div>}
      {saveError && <div role="alert" className="mb-5 flex items-center gap-4 rounded-xl border border-amber-900/50 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">{saveError} <button type="button" onClick={retrySave} disabled={saving} className="underline disabled:opacity-40">Retry save</button></div>}
      {saving && <p role="status" className="mb-4 text-xs text-neutral-500">Saving Trends layout…</p>}
      {status === "error" && <div role="alert" className="mb-5 flex items-center gap-4 rounded-xl border border-amber-900/50 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">Watchlist unavailable. <button type="button" onClick={() => void loadWatchlist()} className="underline">Retry</button></div>}
      {trendError && <p role="alert" className="mb-4 text-sm text-amber-300">{trendError}</p>}
      {trendMessage && <p role="status" className="mb-4 text-sm text-neutral-400">{trendMessage} Scores use delayed regular-session prices.</p>}
      {mode === "reorder" && <p className="mb-4 text-sm text-neutral-400">Drag a handle to rearrange charts. Use arrow keys on a handle to move it with the keyboard.</p>}
      {loadError ? null : status === "loading" ? <p className="py-16 text-center text-neutral-500">Loading Trends…</p> : selectedEntries.length === 0 ? <div className="rounded-2xl border border-dashed border-neutral-700 bg-neutral-900/20 px-6 py-20 text-center">
        <h2 className="text-lg font-medium text-neutral-200">No charts selected</h2>
        <p className="mt-2 text-sm text-neutral-500">Choose stocks from your watchlist to compare them here.</p>
        {entries.length === 0 && <Link href="/dashboard" className="mt-4 inline-block text-sm text-sky-400 hover:underline">Go to Dashboard to add stocks</Link>}
      </div> : <div aria-label="Selected stock charts" className="grid grid-cols-3 items-start gap-4 xl:gap-5">
        {selectedEntries.map((entry, index) => {
          const trendRank = rankById.get(entry.assetId);
          return <div key={entry.assetId} ref={(element) => { if (element) tileRefs.current.set(entry.assetId, element); else tileRefs.current.delete(entry.assetId); }} onDragOver={(event) => dragOver(event, entry.assetId)} onDrop={(event) => { event.preventDefault(); setDraggedId(null); }} className={`min-w-0 rounded-2xl border bg-[#111111] p-4 shadow-lg shadow-black/10 ${draggedId === entry.assetId ? "border-sky-400 opacity-60" : "border-neutral-800"}`}>
          {(mode === "reorder" || mode === "remove") && <div className="mb-3 flex h-7 justify-end">
            {mode === "reorder" ? <button type="button" draggable onDragStart={(event) => { setDraggedId(entry.assetId); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", entry.assetId); }} onDragEnd={() => setDraggedId(null)} onKeyDown={(event) => {
              const deltas: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 };
              if (event.key in deltas) { event.preventDefault(); moveByKeyboard(entry.assetId, deltas[event.key]); }
            }} aria-label={`Move ${entry.symbol} chart`} className="cursor-grab rounded-md px-2 text-lg leading-none text-neutral-400 hover:bg-neutral-800 hover:text-white active:cursor-grabbing">⠿</button>
              : <button type="button" onClick={() => { setTrendRanks(null); setTrendMessage(null); setSelectedIds((current) => current.filter((id) => id !== entry.assetId)); }} aria-label={`Remove ${entry.symbol} chart`} className="rounded-md px-2 text-sm font-medium text-rose-300 hover:bg-rose-400/10">Remove</button>}
          </div>}
          {trendRank && <p className="mb-2 text-xs text-sky-300" title={trendRank.asOf ? `Latest price session ${new Date(trendRank.asOf).toLocaleDateString("en-GB", { timeZone: "America/New_York", dateStyle: "medium" })}; 5-session trend ${trendRank.weekTrendPercent?.toFixed(1)}%; 1-month recovery ${trendRank.monthRecoveryPercent?.toFixed(1)}%` : undefined}>{trendRank.score === null ? "Trend score unavailable" : `Trend #${index + 1} · ${trendRank.score.toFixed(0)}/100`}</p>}
          <StockPriceChart assetId={entry.assetId} range={range} compact watchlistEntry={entry} live={liveBySymbol[entry.symbol]} purchasePriceOverride={purchasePrices[entry.assetId] ?? null} />
        </div>})}
      </div>}
      </div>
    </main>
  );
}
