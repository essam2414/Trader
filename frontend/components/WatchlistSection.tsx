"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WatchlistEntry, WatchlistSearchResult } from "../lib/types";
import { WatchlistItem, type WatchlistMode } from "./WatchlistItem";

const POLL_INTERVAL_MS = 60_000;
export { conciseStockName } from "./WatchlistItem";

export function WatchlistSection() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<WatchlistSearchResult[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [tableMode, setTableMode] = useState<WatchlistMode>("default");
  const [draggedAssetId, setDraggedAssetId] = useState<string | null>(null);
  const [isSavingOrder, setIsSavingOrder] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const listRequest = useRef(0);
  const searchRequest = useRef(0);
  const searchAbort = useRef<AbortController | null>(null);
  const searchContainer = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadWatchlist(), 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadWatchlist();
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
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

  async function persistOrder(orderedEntries: WatchlistEntry[]) {
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
  }

  function dropRow(targetAssetId: string) {
    if (!draggedAssetId || draggedAssetId === targetAssetId || isSavingOrder) return;
    const fromIndex = entries.findIndex((entry) => entry.assetId === draggedAssetId);
    const toIndex = entries.findIndex((entry) => entry.assetId === targetAssetId);
    if (fromIndex < 0 || toIndex < 0) return;
    const orderedEntries = [...entries];
    const [moved] = orderedEntries.splice(fromIndex, 1);
    orderedEntries.splice(toIndex, 0, moved);
    setEntries(orderedEntries);
    setDraggedAssetId(null);
    void persistOrder(orderedEntries);
  }

  return (
    <section className="min-w-0 pt-8" aria-labelledby="watchlist-heading">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
        <h2 id="watchlist-heading" className="text-xl font-semibold tracking-tight text-neutral-100">Watchlist</h2>
        {entries.length > 0 && (
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setTableMode(tableMode === "move" ? "default" : "move")} disabled={tableMode === "delete" || isSavingOrder} className={`rounded-lg px-2 py-1.5 text-sm font-medium transition ${tableMode === "move" ? "bg-neutral-200 text-neutral-950" : "text-neutral-300 hover:bg-neutral-800"}`}>{tableMode === "move" ? "Done" : "Move"}</button>
            <button type="button" onClick={() => setTableMode(tableMode === "delete" ? "default" : "delete")} disabled={tableMode === "move"} className={`rounded-lg px-2 py-1.5 text-sm font-medium transition ${tableMode === "delete" ? "bg-rose-400 text-neutral-950" : "text-rose-300 hover:bg-rose-400/10"}`}>{tableMode === "delete" ? "Done" : "Delete"}</button>
          </div>
        )}
        <div ref={searchContainer} className="relative order-3 w-full min-[700px]:order-none min-[700px]:ml-auto min-[700px]:w-52">
          <label className="sr-only" htmlFor="watchlist-search">Search US equities</label>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>
          <input id="watchlist-search" role="combobox" aria-expanded={isSearchOpen} aria-controls="watchlist-results" value={query} onChange={(event) => updateSearch(event.target.value)} onFocus={() => { if (query.trim()) setIsSearchOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setIsSearchOpen(false); }} placeholder="Search ticker or company" className="h-10 w-full rounded-xl border border-neutral-700 bg-neutral-950 py-0 pl-10 pr-10 text-sm text-neutral-100 outline-none placeholder:text-neutral-600 transition focus:border-neutral-400 focus:ring-2 focus:ring-neutral-500/20" />
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
      {message && <p role="status" className="mt-3 rounded-md bg-amber-400/10 px-3 py-2 text-sm text-amber-300">{message}</p>}
      {isLoading ? <p className="mt-4 text-sm text-neutral-500">Loading watchlist…</p> : entries.length === 0 ? <p className="mt-4 text-sm text-neutral-500">Search for a US equity to begin your watchlist.</p> : (
        <div className="mt-4 space-y-1">
          {entries.map((entry) => (
            <WatchlistItem
              key={entry.assetId}
              entry={entry}
              mode={tableMode}
              isDragging={draggedAssetId === entry.assetId}
              isSavingOrder={isSavingOrder}
              onDragStart={(event, assetId) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", assetId);
                setDraggedAssetId(assetId);
              }}
              onDragOver={(event) => {
                if (tableMode === "move") event.preventDefault();
              }}
              onDrop={dropRow}
              onDragEnd={() => setDraggedAssetId(null)}
              onRemove={(assetId) => void removeAsset(assetId)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
