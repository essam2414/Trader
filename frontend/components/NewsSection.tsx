"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CatalystCard, CatalystDetail, EventRefreshResult, MarketEvent, NewsStatus } from "../lib/types";

const POLL_INTERVAL_MS = 5 * 60_000;

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }).format(new Date(value));
}

function dayLabel(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeZone: "UTC" }).format(
    new Date(`${value}T12:00:00Z`),
  );
}

function sortedNews(items: CatalystCard[]): CatalystCard[] {
  const unique = new Map<number, CatalystCard>();
  for (const item of items) unique.set(item.id, item);
  return [...unique.values()].sort((left, right) =>
    Date.parse(right.releasedAt ?? right.firstSeenAt) - Date.parse(left.releasedAt ?? left.firstSeenAt)
      || right.id - left.id,
  );
}

function StockBadges({ symbols }: { symbols: string[] }) {
  return <div className="flex flex-wrap gap-1.5">
    {symbols.map((symbol) => <span key={symbol} className="rounded-md bg-neutral-800 px-1.5 py-0.5 font-mono text-[11px] font-medium text-neutral-300">{symbol}</span>)}
  </div>;
}

function useDialogKeyboard(onClose: () => void) {
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLButtonElement>("[data-dialog-close]")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>("button, a[href]")];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previousFocus?.focus();
    };
  }, [onClose]);
  return dialogRef;
}

function NewsDetailDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const [detail, setDetail] = useState<CatalystDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useDialogKeyboard(onClose);

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/news/${id}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Details unavailable");
        setDetail(await response.json() as CatalystDetail);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Details unavailable");
      });
    return () => controller.abort();
  }, [id]);

  return <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
    <button type="button" aria-label="Close news detail" onClick={onClose} className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="news-detail-heading" className="relative z-10 flex max-h-[calc(100vh-3rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/70">
      <div className="flex items-start justify-between gap-5 border-b border-neutral-800 px-6 py-5">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-neutral-500">Watchlist catalyst</p>
          <h3 id="news-detail-heading" className="mt-1 text-lg font-semibold text-neutral-100">{detail?.headline ?? "Loading story…"}</h3>
        </div>
        <button data-dialog-close type="button" aria-label="Close news detail" onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xl text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100">×</button>
      </div>
      <div className="space-y-5 overflow-y-auto px-6 py-5 text-sm leading-6 text-neutral-300">
        {error && <p role="status" className="text-amber-300">{error}</p>}
        {detail && <>
          <StockBadges symbols={detail.watchlistSymbols} />
          <p className="text-xs text-neutral-500">{detail.releasedAt ? `Released ${timeLabel(detail.releasedAt)}` : `First found ${timeLabel(detail.firstSeenAt)}`} · First found {timeLabel(detail.firstSeenAt)}</p>
          {detail.status === "pending" ? <p className="text-amber-300">AI summary pending. Read the source before making a decision.</p> : <>
            <p className="whitespace-pre-wrap">{detail.detailSummary}</p>
            {detail.relevanceReason && <p><span className="font-medium text-neutral-100">Why it matters to the watchlist: </span>{detail.relevanceReason}</p>}
            {detail.keyFacts.length > 0 && <div><h4 className="font-medium text-neutral-100">Key facts</h4><ul className="mt-1 list-disc pl-5">{detail.keyFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>}
            {detail.unknowns.length > 0 && <div><h4 className="font-medium text-neutral-100">Not established by sources</h4><ul className="mt-1 list-disc pl-5">{detail.unknowns.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>}
          </>}
          <div><h4 className="font-medium text-neutral-100">Sources</h4><ul className="mt-2 space-y-2">{detail.sources.map((source) => <li key={`${source.provider}:${source.url}`}><a href={source.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline hover:text-sky-200">{source.title}</a><span className="ml-2 text-xs text-neutral-500">{source.provider}{source.publishedAt ? ` · ${timeLabel(source.publishedAt)}` : ""}</span></li>)}</ul></div>
        </>}
      </div>
    </section>
  </div>;
}

function EventDetailDialog({ event, onClose }: { event: MarketEvent; onClose: () => void }) {
  const dialogRef = useDialogKeyboard(onClose);
  return <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
    <button type="button" aria-label="Close event detail" onClick={onClose} className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="event-detail-heading" className="relative z-10 w-full max-w-xl rounded-2xl border border-neutral-700 bg-neutral-950 p-6 shadow-2xl">
      <div className="flex justify-between gap-4"><h3 id="event-detail-heading" className="text-lg font-semibold text-neutral-100">{event.title}</h3><button data-dialog-close type="button" aria-label="Close event detail" onClick={onClose} className="text-xl text-neutral-400">×</button></div>
      <p className="mt-3 text-sm text-neutral-300">{event.startsAt ? timeLabel(event.startsAt) : dayLabel(event.eventDate)} · {event.dateStatus}</p>
      {event.previousEventDate && <p className="mt-2 text-sm text-amber-300">Previously scheduled for {dayLabel(event.previousEventDate)}</p>}
      <div className="mt-3"><StockBadges symbols={event.watchlistSymbols} /></div>
      {event.scope === "us_market" && <p className="mt-3 text-sm text-neutral-400">US market event</p>}
      <p className="mt-5 text-sm text-neutral-400">Last verified {timeLabel(event.lastVerifiedAt)}</p>
      <a href={event.sourceUrl} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-sm text-sky-300 underline">View schedule source</a>
    </section>
  </div>;
}

export function NewsSection() {
  const [tab, setTab] = useState<"news" | "events">("news");
  const [articles, setArticles] = useState<CatalystCard[]>([]);
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [status, setStatus] = useState<NewsStatus | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<number | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<MarketEvent | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [isRefreshingEvents, setIsRefreshingEvents] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const getJson = async <T,>(path: string): Promise<T> => {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(path);
      return await response.json() as T;
    };
    const [newsResult, eventsResult, statusResult] = await Promise.allSettled([
      getJson<CatalystCard[]>("/api/news"),
      getJson<MarketEvent[]>("/api/events"),
      getJson<NewsStatus>("/api/news/status"),
    ]);
    if (newsResult.status === "fulfilled") setArticles(sortedNews(newsResult.value));
    if (eventsResult.status === "fulfilled") setEvents(eventsResult.value);
    if (statusResult.status === "fulfilled") setStatus(statusResult.value);
    setMessage(
      [newsResult, eventsResult, statusResult].some((result) => result.status === "rejected")
        ? "Some briefing data is unavailable. Previous results are shown where available."
        : null,
    );
    setIsLoading(false);
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const interval = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, POLL_INTERVAL_MS);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, [load]);

  async function refreshEvents() {
    setTab("events");
    setIsRefreshingEvents(true);
    setRefreshMessage(null);
    try {
      const response = await fetch("/api/events", { method: "POST", cache: "no-store" });
      if (!response.ok) {
        throw new Error(response.status === 409
          ? "Events are already refreshing. Try again shortly."
          : response.status === 503
            ? "Events collection is disabled."
            : "Could not refresh events from their sources.");
      }
      const result = await response.json() as EventRefreshResult;
      const eventsResponse = await fetch("/api/events", { cache: "no-store" });
      if (!eventsResponse.ok) throw new Error("Events were collected, but the updated list could not be loaded.");
      setEvents(await eventsResponse.json() as MarketEvent[]);
      setRefreshMessage(result.failedSources.length > 0
        ? `Some event sources are unavailable: ${result.failedSources.join(", ")}.`
        : null);
    } catch (reason) {
      setRefreshMessage(reason instanceof Error ? reason.message : "Could not refresh events.");
    } finally {
      setIsRefreshingEvents(false);
    }
  }

  return <section className="flex min-h-0 min-w-0 flex-col pt-6" aria-label="News" aria-labelledby="news-heading">
    <div className="flex shrink-0 items-center justify-between gap-4">
      <h2 id="news-heading" className="text-xl font-semibold tracking-tight text-neutral-100">Analysis</h2>
      <div className="flex shrink-0 items-center gap-3">
        <button type="button" aria-label="Refresh events" title="Refresh events from sources" disabled={isRefreshingEvents} onClick={() => void refreshEvents()} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-neutral-800 text-neutral-400 transition hover:border-neutral-600 hover:bg-neutral-800 hover:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-neutral-400/40 disabled:cursor-wait disabled:opacity-60">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={`h-5 w-5 ${isRefreshingEvents ? "animate-spin" : ""}`}><path d="M20 11a8 8 0 0 0-14.5-4.7L3 9" /><path d="M3 4v5h5" /><path d="M4 13a8 8 0 0 0 14.5 4.7L21 15" /><path d="M16 15h5v5" /></svg>
        </button>
        <div role="tablist" aria-label="News and events" className="flex rounded-lg border border-neutral-800 p-1 text-sm">
          <button type="button" role="tab" aria-selected={tab === "news"} onClick={() => setTab("news")} className={`rounded-md px-3 py-1 ${tab === "news" ? "bg-neutral-800 text-neutral-100" : "text-neutral-400"}`}>News</button>
          <button type="button" role="tab" aria-selected={tab === "events"} onClick={() => setTab("events")} className={`rounded-md px-3 py-1 ${tab === "events" ? "bg-neutral-800 text-neutral-100" : "text-neutral-400"}`}>Events</button>
        </div>
      </div>
    </div>
    <div className="mt-2 shrink-0 text-xs text-neutral-500">{status?.lastSuccessfulRunAt ? `Last collected ${timeLabel(status.lastSuccessfulRunAt)}` : "Waiting for first collection"}</div>
    {status && status.failedSources.length > 0 && <p role="status" className="mt-2 rounded-md bg-amber-400/10 px-3 py-2 text-xs text-amber-300">Some sources are unavailable: {status.failedSources.join(", ")}</p>}
    {status && status.pendingSummaries > 0 && <p role="status" className="mt-2 rounded-md bg-amber-400/10 px-3 py-2 text-xs text-amber-300">{status.pendingSummaries} source-backed {status.pendingSummaries === 1 ? "story has" : "stories have"} a summary pending.</p>}
    {message && <p role="status" className="mt-2 rounded-md bg-amber-400/10 px-3 py-2 text-sm text-amber-300">{message}</p>}
    {refreshMessage && <p role="status" className="mt-2 text-sm text-neutral-300">{refreshMessage}</p>}
    <div aria-label={tab === "news" ? "News articles" : "Upcoming events"} className="dashboard-pane-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto pr-3 pb-6">
      {isLoading ? <p className="text-sm text-neutral-500">Loading…</p> : tab === "news" ? (
        articles.length === 0 ? <p className="text-sm text-neutral-500">No watchlist catalysts collected yet.</p> :
          <div className="grid grid-cols-2 gap-3">{articles.map((article) => <button key={article.id} type="button" onClick={() => setSelectedArticle(article.id)} className="min-w-0 rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 text-left transition hover:border-neutral-600 hover:bg-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-400/40">
            <StockBadges symbols={article.watchlistSymbols} />
            <h3 className="mt-3 text-sm font-semibold leading-5 text-neutral-100">{article.headline}</h3>
            {article.shortSummary && <p className="mt-2 line-clamp-2 text-xs leading-5 text-neutral-400">{article.shortSummary}</p>}
            <p className="mt-3 text-xs text-neutral-500">{article.releasedAt ? "Released" : "First found"} {timeLabel(article.releasedAt ?? article.firstSeenAt)} · {article.category} · {article.direction}{article.status === "pending" ? " · Summary pending" : ""}</p>
          </button>)}</div>
      ) : events.length === 0 ? <p className="text-sm text-neutral-500">No upcoming events found yet.</p> :
        <div className="grid grid-cols-2 gap-3">{events.map((event) => <button key={event.id} type="button" onClick={() => setSelectedEvent(event)} className={`min-w-0 rounded-xl border p-4 text-left transition focus:outline-none focus:ring-2 ${event.category === "earnings" ? "border-orange-700/70 bg-orange-900/60 hover:border-orange-500 hover:bg-orange-900/75 focus:ring-orange-400/40" : "border-neutral-800 bg-neutral-900/50 hover:border-neutral-600 hover:bg-neutral-900 focus:ring-neutral-400/40"}`}>
          {event.scope === "watchlist" ? <StockBadges symbols={event.watchlistSymbols} /> : <span className="text-xs font-medium text-sky-300">US market</span>}
          <h3 className="mt-3 text-sm font-semibold leading-5 text-neutral-100">{event.title}</h3>
          <p className="mt-3 text-xs text-neutral-500">{event.startsAt ? timeLabel(event.startsAt) : dayLabel(event.eventDate)} · {event.dateStatus}</p>
        </button>)}</div>}
    </div>
    {selectedArticle !== null && <NewsDetailDialog id={selectedArticle} onClose={() => setSelectedArticle(null)} />}
    {selectedEvent && <EventDetailDialog event={selectedEvent} onClose={() => setSelectedEvent(null)} />}
  </section>;
}
