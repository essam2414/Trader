"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import type { MarketSession, MarketSessionPhase, WatchlistEntry, WatchlistSearchResult } from "../lib/types";
import { WatchlistItem, type WatchlistMode } from "./WatchlistItem";

const MARKET_SESSION_REFRESH_INTERVAL_MS = 60_000;
export { conciseStockName } from "./WatchlistItem";

type DragState = {
  assetId: string;
  pointerId: number;
  offsetY: number;
  width: number;
  x: number;
  y: number;
};

type WatchlistQuoteEvent = {
  symbol: string;
  price: number;
  sourceTimestamp: string;
  sourceType: string;
  freshness: "fresh" | "stale" | "unavailable";
  isExtendedHours: boolean;
};

function isWatchlistQuoteEvent(value: unknown): value is WatchlistQuoteEvent {
  return Boolean(
    value
      && typeof value === "object"
      && "symbol" in value
      && "price" in value
      && "sourceTimestamp" in value
      && "sourceType" in value
      && "freshness" in value
      && "isExtendedHours" in value
      && typeof value.symbol === "string"
      && typeof value.price === "number"
      && typeof value.sourceTimestamp === "string"
      && typeof value.sourceType === "string"
      && ["fresh", "stale", "unavailable"].includes(String(value.freshness))
      && typeof value.isExtendedHours === "boolean",
  );
}

function applyQuoteEvent(entries: WatchlistEntry[], update: WatchlistQuoteEvent): WatchlistEntry[] {
  return entries.map((entry) => {
    if (entry.symbol !== update.symbol) return entry;
    const previousClose = entry.quote.previousClose;
    const dollarChange = previousClose === null ? null : update.price - previousClose;
    const percentChange = previousClose === null || previousClose === 0
      ? null
      : ((update.price - previousClose) / previousClose) * 100;
    return {
      ...entry,
      quote: {
        ...entry.quote,
        price: update.price,
        dollarChange,
        percentChange,
        feed: "iex",
        sourceTimestamp: update.sourceTimestamp,
        sourceType: update.sourceType,
        freshness: update.freshness,
        isExtendedHours: update.isExtendedHours,
      },
    };
  });
}

const londonTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const londonDayAndTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const phaseLabels: Record<Exclude<MarketSessionPhase, "closed">, string> = {
  pre_market: "pre-market",
  regular: "regular hours",
  after_hours: "after-hours",
  overnight: "overnight",
};

function isMarketSession(value: unknown): value is MarketSession {
  return Boolean(
    value
      && typeof value === "object"
      && "phase" in value
      && ["pre_market", "regular", "after_hours", "overnight", "closed"].includes(
        String(value.phase),
      ),
  );
}

function marketSessionReminder(session: MarketSession | null, unavailable: boolean): string {
  if (unavailable) return "US market schedule unavailable";
  if (!session) return "Loading US market session…";
  if (session.phase === "closed") {
    if (!session.nextPhase || !session.nextPhaseStartsAt) return "US market closed";
    return `US market closed · ${phaseLabels[session.nextPhase]} ${londonDayAndTime.format(new Date(session.nextPhaseStartsAt))} UK`;
  }
  if (!session.endsAt) return `US ${phaseLabels[session.phase]}`;
  const verb = session.phase === "regular" ? (session.isEarlyClose ? "early close" : "closes") : "ends";
  return `US ${phaseLabels[session.phase]} · ${verb} ${londonTime.format(new Date(session.endsAt))} UK`;
}

function marketSessionTone(session: MarketSession | null, unavailable: boolean): string {
  if (unavailable || !session || session.phase === "closed") return "bg-neutral-500";
  if (session.phase === "pre_market") return "bg-orange-400";
  if (session.phase === "regular") return "bg-green-400";
  if (session.phase === "after_hours") return "bg-pink-400";
  return "bg-blue-400";
}

function marketSessionTextTone(session: MarketSession | null, unavailable: boolean): string {
  if (unavailable || !session || session.phase === "closed") return "text-neutral-400";
  if (session.phase === "pre_market") return "text-orange-300";
  if (session.phase === "regular") return "text-green-300";
  if (session.phase === "after_hours") return "text-pink-300";
  return "text-blue-300";
}

export function WatchlistSection() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<WatchlistSearchResult[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [tableMode, setTableMode] = useState<WatchlistMode>("default");
  const [draggedAssetId, setDraggedAssetId] = useState<string | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [isSavingOrder, setIsSavingOrder] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [marketSession, setMarketSession] = useState<MarketSession | null>(null);
  const [isMarketSessionUnavailable, setIsMarketSessionUnavailable] = useState(false);
  const listRequest = useRef(0);
  const searchRequest = useRef(0);
  const searchAbort = useRef<AbortController | null>(null);
  const searchContainer = useRef<HTMLDivElement | null>(null);
  const entryElements = useRef(new Map<string, HTMLDivElement>());
  const previousEntryTops = useRef(new Map<string, number>());
  const entryAnimations = useRef(new Map<string, Animation>());
  const entriesRef = useRef(entries);
  const dragStateRef = useRef<DragState | null>(null);
  const dragStartEntries = useRef<WatchlistEntry[] | null>(null);
  const previewTarget = useRef<string | null>(null);
  const hasDropped = useRef(false);
  const entryOrder = entries.map((entry) => entry.assetId).join("\u0000");

  useLayoutEffect(() => {
    const nextEntryTops = new Map<string, number>();
    const entryIds = entryOrder ? entryOrder.split("\u0000") : [];
    for (const assetId of entryIds) {
      const element = entryElements.current.get(assetId);
      if (!element) continue;
      const top = element.getBoundingClientRect().top;
      const previousTop = previousEntryTops.current.get(assetId);
      if (previousTop !== undefined && previousTop !== top && typeof element.animate === "function") {
        entryAnimations.current.get(assetId)?.cancel();
        const animation = element.animate(
          [{ transform: `translateY(${previousTop - top}px)` }, { transform: "translateY(0)" }],
          { duration: 220, easing: "cubic-bezier(0.2, 0, 0, 1)" },
        );
        entryAnimations.current.set(assetId, animation);
      }
      nextEntryTops.set(assetId, top);
    }
    previousEntryTops.current = nextEntryTops;
  }, [entryOrder]);

  const loadWatchlist = useCallback(async () => {
    const requestId = ++listRequest.current;
    try {
      const response = await fetch("/api/watchlist", { cache: "no-store" });
      const body: unknown = await response.json();
      if (requestId !== listRequest.current) return;
      if (!response.ok) {
        setMessage(typeof body === "object" && body && "detail" in body ? String(body.detail) : "Watchlist unavailable");
        return;
      }
      setEntries(body as WatchlistEntry[]);
      setMessage(null);
    } catch {
      if (requestId === listRequest.current) setMessage("Watchlist unavailable");
    } finally {
      if (requestId === listRequest.current) setIsLoading(false);
    }
  }, []);

  const loadMarketSession = useCallback(async () => {
    try {
      const response = await fetch("/api/market-session", { cache: "no-store" });
      const body: unknown = await response.json();
      if (!response.ok || !isMarketSession(body)) {
        setIsMarketSessionUnavailable(true);
        return;
      }
      setMarketSession(body);
      setIsMarketSessionUnavailable(false);
    } catch {
      setIsMarketSessionUnavailable(true);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadWatchlist();
      void loadMarketSession();
    }, 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadMarketSession();
      }
    }, MARKET_SESSION_REFRESH_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadMarketSession, loadWatchlist]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let source: EventSource | null = null;
    let reconnectTimeout: number | undefined;
    let stopped = false;

    const disconnect = () => {
      source?.close();
      source = null;
    };

    const connect = () => {
      if (stopped || document.visibilityState !== "visible") return;
      disconnect();
      source = new EventSource("/api/watchlist/stream");
      source.addEventListener("quote", (event) => {
        try {
          const update: unknown = JSON.parse((event as MessageEvent<string>).data);
          if (isWatchlistQuoteEvent(update)) setEntries((current) => applyQuoteEvent(current, update));
        } catch {
          // Ignore malformed provider events; the next valid trade will replace this price.
        }
      });
      source.onerror = () => {
        disconnect();
        if (!stopped && document.visibilityState === "visible") {
          reconnectTimeout = window.setTimeout(connect, 2_000);
        }
      };
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void loadWatchlist();
        connect();
      } else {
        disconnect();
      }
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      stopped = true;
      if (reconnectTimeout !== undefined) window.clearTimeout(reconnectTimeout);
      disconnect();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [loadWatchlist]);

  useEffect(() => {
    const closeWhenClickingAway = (event: PointerEvent) => {
      if (searchContainer.current && !searchContainer.current.contains(event.target as Node)) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeWhenClickingAway);
    return () => document.removeEventListener("pointerdown", closeWhenClickingAway);
  }, []);

  useEffect(() => {
    const term = query.trim();
    const requestId = ++searchRequest.current;
    searchAbort.current?.abort();
    if (!term) return;
    const timeout = window.setTimeout(async () => {
      const controller = new AbortController();
      searchAbort.current = controller;
      try {
        const response = await fetch(`/api/watchlist/search?q=${encodeURIComponent(term)}`, { signal: controller.signal });
        const body: unknown = await response.json();
        if (requestId === searchRequest.current && response.ok) {
          setResults(body as WatchlistSearchResult[]);
          setIsSearching(false);
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError" && requestId === searchRequest.current) {
          setResults([]);
          setIsSearching(false);
        }
      }
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [query]);

  async function addAsset(asset: WatchlistSearchResult) {
    const response = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId: asset.assetId }),
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      setMessage(typeof body === "object" && body && "detail" in body ? String(body.detail) : "Could not add equity");
      return;
    }
    setQuery("");
    setIsSearchOpen(false);
    setIsSearching(false);
    await loadWatchlist();
  }

  function updateSearch(value: string) {
    const hasQuery = Boolean(value.trim());
    setQuery(value);
    setIsSearchOpen(hasQuery);
    setIsSearching(hasQuery);
    if (!hasQuery) setResults([]);
  }

  async function removeAsset(assetId: string) {
    const response = await fetch(`/api/watchlist/${encodeURIComponent(assetId)}`, { method: "DELETE" });
    if (!response.ok && response.status !== 404) {
      setMessage("Could not remove equity");
      return;
    }
    setEntries((current) => current.filter((entry) => entry.assetId !== assetId));
  }

  const persistOrder = useCallback(async (orderedEntries: WatchlistEntry[]) => {
    setIsSavingOrder(true);
    try {
      const response = await fetch("/api/watchlist/order", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assetIds: orderedEntries.map((entry) => entry.assetId) }),
      });
      if (!response.ok) {
        setMessage("Could not save the new watchlist order");
        void loadWatchlist();
      }
    } catch {
      setMessage("Could not save the new watchlist order");
      void loadWatchlist();
    } finally {
      setIsSavingOrder(false);
    }
  }, [loadWatchlist]);

  function previewRowMove(targetAssetId: string, pointerY: number, targetBounds: DOMRect) {
    const startingEntries = dragStartEntries.current;
    if (
      !draggedAssetId
      || !startingEntries
      || draggedAssetId === targetAssetId
      || previewTarget.current === targetAssetId
      || isSavingOrder
    ) return;

    const placeAfterTarget = pointerY >= targetBounds.top + targetBounds.height / 2;
    const fromIndex = startingEntries.findIndex((entry) => entry.assetId === draggedAssetId);
    const targetIndex = startingEntries.findIndex((entry) => entry.assetId === targetAssetId);
    if (fromIndex < 0 || targetIndex < 0) return;

    const nextEntries = [...startingEntries];
    const [moved] = nextEntries.splice(fromIndex, 1);
    const targetIndexAfterRemoval = nextEntries.findIndex((entry) => entry.assetId === targetAssetId);
    const insertionIndex = targetIndexAfterRemoval + (placeAfterTarget ? 1 : 0);
    nextEntries.splice(insertionIndex, 0, moved);
    if (nextEntries.every((entry, index) => entry.assetId === entriesRef.current[index]?.assetId)) return;

    previewTarget.current = targetAssetId;
    entriesRef.current = nextEntries;
    setEntries(nextEntries);
  }

  const cancelPointerDragById = useCallback((pointerId: number) => {
    const activeDrag = dragStateRef.current;
    if (!activeDrag || activeDrag.pointerId !== pointerId) return;
    if (!hasDropped.current && dragStartEntries.current) {
      entriesRef.current = dragStartEntries.current;
      setEntries(dragStartEntries.current);
    }
    dragStartEntries.current = null;
    previewTarget.current = null;
    hasDropped.current = false;
    dragStateRef.current = null;
    setDraggedAssetId(null);
    setDragState(null);
  }, []);

  function startPointerDrag(event: ReactPointerEvent<HTMLDivElement>, assetId: string) {
    const bounds = event.currentTarget.getBoundingClientRect();
    dragStartEntries.current = entries;
    entriesRef.current = entries;
    previewTarget.current = null;
    hasDropped.current = false;
    const nextDragState = {
      assetId,
      pointerId: event.pointerId,
      offsetY: event.clientY - bounds.top,
      width: bounds.width,
      x: bounds.left,
      y: bounds.top,
    };
    dragStateRef.current = nextDragState;
    setDragState(nextDragState);
    setDraggedAssetId(assetId);
  }

  function movePointerDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const activeDrag = dragStateRef.current;
    if (!activeDrag || event.pointerId !== activeDrag.pointerId) return;
    const nextDragState = {
      ...activeDrag,
      y: event.clientY - activeDrag.offsetY,
    };
    dragStateRef.current = nextDragState;
    setDragState(nextDragState);

    const target = document.elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>("[data-watchlist-entry]");
    const targetAssetId = target?.dataset.watchlistEntry;
    if (targetAssetId && targetAssetId !== activeDrag.assetId) {
      previewRowMove(targetAssetId, event.clientY, target.getBoundingClientRect());
    }
  }

  const dropPointerDragById = useCallback((pointerId: number) => {
    const activeDrag = dragStateRef.current;
    if (!activeDrag || activeDrag.pointerId !== pointerId || hasDropped.current) return;
    hasDropped.current = true;
    dragStateRef.current = null;
    setDraggedAssetId(null);
    setDragState(null);
    void persistOrder(entriesRef.current);
  }, [persistOrder]);

  function dropPointerDrag(event: ReactPointerEvent<HTMLDivElement>) {
    dropPointerDragById(event.pointerId);
  }

  function cancelPointerDrag(event: ReactPointerEvent<HTMLDivElement>) {
    cancelPointerDragById(event.pointerId);
  }

  useEffect(() => {
    const handlePointerUp = (event: globalThis.PointerEvent) => dropPointerDragById(event.pointerId);
    const handlePointerCancel = (event: globalThis.PointerEvent) => cancelPointerDragById(event.pointerId);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerCancel);
    return () => {
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerCancel);
    };
  }, [cancelPointerDragById, dropPointerDragById]);

  function dragStyleFor(entry: WatchlistEntry): CSSProperties | undefined {
    if (!dragState || dragState.assetId !== entry.assetId) return undefined;
    return {
      position: "fixed",
      top: dragState.y,
      left: dragState.x,
      width: dragState.width,
      zIndex: 30,
      pointerEvents: "none",
      touchAction: "none",
    };
  }

  return (
    <section className="mr-3 flex min-h-0 min-w-0 flex-col pt-6" aria-labelledby="watchlist-heading">
      <div className="shrink-0 flex flex-nowrap items-start gap-x-8">
        <div className="relative shrink-0 pb-8">
          <h2 id="watchlist-heading" className="text-xl font-semibold tracking-tight text-neutral-100">Watchlist</h2>
          <p aria-live="polite" className={`absolute left-0 top-10 flex w-[300px] items-center gap-1.5 overflow-hidden text-sm whitespace-nowrap ${marketSessionTextTone(marketSession, isMarketSessionUnavailable)}`}>
            <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${marketSessionTone(marketSession, isMarketSessionUnavailable)}`} />
            <span className="truncate">{marketSessionReminder(marketSession, isMarketSessionUnavailable)}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-5">
          {entries.length > 0 && (
            <>
              <button type="button" onClick={() => setTableMode(tableMode === "move" ? "default" : "move")} disabled={tableMode === "delete" || isSavingOrder} className={`rounded-lg px-2 py-1.5 text-sm font-medium transition ${tableMode === "move" ? "bg-neutral-200 text-neutral-950" : "text-neutral-300 hover:bg-neutral-800"}`}>{tableMode === "move" ? "Done" : "Move"}</button>
              <button type="button" onClick={() => setTableMode(tableMode === "delete" ? "default" : "delete")} disabled={tableMode === "move"} className={`rounded-lg px-2 py-1.5 text-sm font-medium transition ${tableMode === "delete" ? "bg-rose-400 text-neutral-950" : "text-rose-300 hover:bg-rose-400/10"}`}>{tableMode === "delete" ? "Done" : "Delete"}</button>
            </>
          )}
          <div ref={searchContainer} className="relative w-32">
          <label className="sr-only" htmlFor="watchlist-search">Search US equities</label>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>
          <input id="watchlist-search" role="combobox" aria-expanded={isSearchOpen} aria-controls="watchlist-results" value={query} onChange={(event) => updateSearch(event.target.value)} onFocus={() => { if (query.trim()) setIsSearchOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setIsSearchOpen(false); }} placeholder="Search ticker or company" className="h-8 w-full rounded-xl border border-neutral-700 bg-neutral-950 py-0 pl-10 pr-10 text-sm text-neutral-100 outline-none placeholder:text-neutral-600 transition focus:border-neutral-400 focus:ring-2 focus:ring-neutral-500/20" />
          {query && <button type="button" onClick={() => updateSearch("")} aria-label="Clear search" className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-100"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}
          {isSearchOpen && (
            <div id="watchlist-results" role="listbox" className="absolute z-10 mt-2 w-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/50">
              <div className="border-b border-neutral-800 px-3 py-2 text-xs font-medium uppercase tracking-wider text-neutral-500">Matching equities</div>
              {isSearching ? <p className="px-3 py-4 text-sm text-neutral-500">Searching…</p> : results.length === 0 ? <p className="px-3 py-4 text-sm text-neutral-500">No matching US equity found.</p> : <ul className="max-h-72 overflow-auto p-1">
              {results.map((result) => (
                <li key={result.assetId}>
                  <button type="button" role="option" aria-selected="false" onClick={() => void addAsset(result)} className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-neutral-800 focus:bg-neutral-800 focus:outline-none">
                    <span className="flex h-9 min-w-9 items-center justify-center rounded-lg bg-neutral-800 px-2 font-mono text-xs font-semibold text-neutral-100">{result.symbol}</span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-neutral-100">{result.name}</span><span className="block text-xs text-neutral-500">{result.exchange}</span></span>
                    <span aria-hidden="true" className="text-lg text-neutral-500">+</span>
                  </button>
                </li>
              ))}
              </ul>}
            </div>
          )}
          </div>
        </div>
      </div>
      <div aria-label="Watchlist entries" className="dashboard-pane-scrollbar mt-2 min-h-0 flex-1 overflow-y-auto pr-3 pb-6">
        {message && <p role="status" className="rounded-md bg-amber-400/10 px-3 py-2 text-sm text-amber-300">{message}</p>}
      {isLoading ? <p className="mt-4 text-sm text-neutral-500">Loading watchlist…</p> : entries.length === 0 ? <p className="mt-4 text-sm text-neutral-500">Search for up to 20 US equities to begin your watchlist.</p> : (
        <div className="mt-2 space-y-1">
          {entries.map((entry) => {
            const isDragging = draggedAssetId === entry.assetId;
            const registerEntryElement = (element: HTMLDivElement | null) => {
              if (element) entryElements.current.set(entry.assetId, element);
              else entryElements.current.delete(entry.assetId);
            };
            const item = (
              <WatchlistItem
                entry={entry}
                mode={tableMode}
                isDragging={isDragging}
                isSavingOrder={isSavingOrder}
                onRemove={(assetId) => void removeAsset(assetId)}
                itemRef={isDragging ? undefined : registerEntryElement}
                onPointerDragStart={startPointerDrag}
                onPointerDragMove={movePointerDrag}
                onPointerDragEnd={dropPointerDrag}
                onPointerDragCancel={cancelPointerDrag}
                dragStyle={dragStyleFor(entry)}
              />
            );

            if (!isDragging) return <div key={entry.assetId}>{item}</div>;

            return (
              <div key={entry.assetId} ref={registerEntryElement} className="min-h-[68px]">
                {item}
              </div>
            );
          })}
        </div>
      )}
      </div>
    </section>
  );
}
