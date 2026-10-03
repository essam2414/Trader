"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CatalystCard, CatalystDetail, EventRefreshResult, EventStatus, MarketEvent, NewsRefreshResult, NewsStatus, SourceError } from "../lib/types";

const POLL_INTERVAL_MS = 5 * 60_000;
const PENDING_POLL_INTERVAL_MS = 30_000;
const RUN_COMPLETION_POLL_MS = 10_000;

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
    (right.releasedAt ? 1 : 0) - (left.releasedAt ? 1 : 0)
      || Date.parse(right.releasedAt ?? right.firstSeenAt) - Date.parse(left.releasedAt ?? left.firstSeenAt)
      || right.id - left.id,
  );
}

function releaseLabel(value: string, precision?: "minute" | "date" | null): string {
  return precision === "date" ? dayLabel(value.slice(0, 10)) : timeLabel(value);
}

function dateStatusLabel(status: string): string {
  return status === "body_text_published_date" ? "date from article text" : status.replaceAll("_", " ");
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

function NewsDetailDialog({ id, version, onClose }: { id: number; version?: string; onClose: () => void }) {
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
  }, [id, version]);

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
          <p className="text-xs text-neutral-500">{detail.releasedAt ? `Released ${releaseLabel(detail.releasedAt, detail.releaseDatePrecision)}` : "Publication date unverified"}{detail.eventDate ? ` · Catalyst date in article ${dayLabel(detail.eventDate)}` : ""} · First found {timeLabel(detail.firstSeenAt)}</p>
          {detail.status === "pending" ? <p className="text-amber-300">AI summary pending. Read the source before making a decision.</p> : <>
            <p className="whitespace-pre-wrap">{detail.detailSummary}</p>
            {detail.relevanceReason && <p><span className="font-medium text-neutral-100">Why it matters to the watchlist: </span>{detail.relevanceReason}</p>}
            {detail.keyFacts.length > 0 && <div><h4 className="font-medium text-neutral-100">Key facts</h4><ul className="mt-1 list-disc pl-5">{detail.keyFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>}
            {detail.unknowns.length > 0 && <div><h4 className="font-medium text-neutral-100">Not established by sources</h4><ul className="mt-1 list-disc pl-5">{detail.unknowns.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>}
          </>}
          <div><h4 className="font-medium text-neutral-100">Sources</h4><ul className="mt-2 space-y-2">{detail.sources.map((source) => <li key={`${source.provider}:${source.url}`}><a href={source.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline hover:text-sky-200">{source.title}</a><span className="ml-2 text-xs text-neutral-500">{source.provider}{source.publishedAt ? ` · ${releaseLabel(source.publishedAt, source.datePrecision)} · ${dateStatusLabel(source.dateStatus)}` : ` · ${dateStatusLabel(source.dateStatus)}`}{source.eventDate ? ` · Catalyst date ${dayLabel(source.eventDate)}` : ""}</span></li>)}</ul></div>
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

function sourceGroup(source: string): string {
  if (source.startsWith("openai_web:")) return "OpenAI web search";
  if (source.startsWith("rss:")) return "RSS feeds";
  if (source.startsWith("gdelt")) return "GDELT";
  return "Other sources";
}

function sourceName(source: string): string {
  const names: Record<string, string> = {
    sec: "SEC filings",
    "rss:ir_be": "Bloom Energy",
    "rss:prnewswire": "PR Newswire",
  };
  if (names[source]) return names[source];
  const name = source.split(":").slice(1).join(":") || source;
  return name.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableError(message: string): { summary: string; retryAt: string | null } {
  const [detail, retryAt] = message.split(/; retry after /i, 2);
  const firstLine = detail.split(/\r?\n/)[0].trim();
  const httpError = firstLine.match(/^(?:Client|Server) error '([^']+)' for url /i);
  return { summary: httpError?.[1] ?? firstLine, retryAt: retryAt ?? null };
}

function CollectionErrorIndicator({ section, sourceErrors, notices, lastRun }: {
  section: "news" | "events";
  sourceErrors: SourceError[];
  notices: string[];
  lastRun?: NewsStatus["lastRun"];
}) {
  const [openMode, setOpenMode] = useState<"closed" | "preview" | "pinned">("closed");
  const containerRef = useRef<HTMLDivElement>(null);
  const title = `${section === "news" ? "News" : "Events"} collection errors`;
  const isOpen = openMode !== "closed";

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpenMode("closed");
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMode("closed");
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  if (sourceErrors.length === 0 && notices.length === 0 && !lastRun?.failed && !lastRun?.skipped) return null;

  const groups = ["OpenAI web search", "RSS feeds", "GDELT", "Other sources"]
    .map((name) => ({ name, errors: sourceErrors.filter((error) => sourceGroup(error.source) === name) }))
    .filter((group) => group.errors.length > 0);

  return <div
    ref={containerRef}
    className="relative"
    onMouseEnter={() => setOpenMode((mode) => mode === "closed" ? "preview" : mode)}
    onMouseLeave={() => setOpenMode((mode) => mode === "preview" ? "closed" : mode)}
  >
    <button
      type="button"
      aria-label={title}
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      onClick={() => setOpenMode((mode) => mode === "pinned" ? "closed" : "pinned")}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-orange-400 transition hover:bg-orange-400/10 focus:outline-none focus:ring-2 focus:ring-orange-400/40"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none">
        <path d="M10.5 3.2a1.8 1.8 0 0 1 3 0l8.8 14c.8 1.2-.1 2.8-1.5 2.8H3.2c-1.4 0-2.3-1.6-1.5-2.8l8.8-14Z" fill="currentColor" />
        <path d="M12 8v6.5" stroke="#171717" strokeWidth="2" strokeLinecap="round" />
        <circle cx="12" cy="17" r="1.1" fill="#171717" />
      </svg>
    </button>
    {isOpen && <div role="dialog" aria-label={title} className="absolute right-0 top-full z-30 mt-2 flex max-h-[min(30rem,calc(100vh-20rem))] w-[28rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-orange-500/40 bg-neutral-900 text-left text-xs text-neutral-200 shadow-xl shadow-black/50">
      <div className="shrink-0 border-b border-neutral-700 px-4 py-3">
        <p className="font-semibold text-orange-300">{title}</p>
        {lastRun && <p className="mt-1 text-neutral-400">Last run: {lastRun.succeeded} succeeded · {lastRun.failed} failed · {lastRun.skipped} deferred</p>}
        {lastRun && lastRun.newSourceItems !== null && lastRun.newSourceItems !== undefined && lastRun.newCards !== null && lastRun.newCards !== undefined && <p className="mt-1 text-neutral-400">{lastRun.newSourceItems} new source {lastRun.newSourceItems === 1 ? "item" : "items"} · {lastRun.newCards} new {lastRun.newCards === 1 ? "card" : "cards"}</p>}
        {sourceErrors.length > 0 && <p className="mt-1 text-neutral-300">Coverage incomplete · {sourceErrors.length} {sourceErrors.length === 1 ? "source has an unresolved error" : "sources have unresolved errors"}</p>}
      </div>
      <div role="region" aria-label="Error details" tabIndex={0} className="collection-error-scrollbar min-h-0 overflow-y-auto overscroll-contain px-4 py-3 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-neutral-600">
        {notices.length > 0 && <div className="mb-4"><h3 className="font-semibold text-neutral-100">Collection notices</h3><ul className="mt-2 space-y-2">{notices.map((notice) => <li key={notice} className="break-words rounded-lg bg-neutral-800/70 px-3 py-2 leading-5">{notice}</li>)}</ul></div>}
        {groups.map((group) => <div key={group.name} className="mb-4 last:mb-0">
          <h3 className="mb-2 flex items-center justify-between border-b border-neutral-700 pb-1 font-semibold text-neutral-100"><span>{group.name}</span><span className="text-neutral-500">{group.errors.length}</span></h3>
          <ul className="space-y-2">{group.errors.map(({ source, message }) => {
            const { summary, retryAt } = readableError(message);
            return <li key={source} className="rounded-lg bg-neutral-800/70 px-3 py-2 leading-5">
              <p className="font-medium text-neutral-100">{sourceName(source)}</p>
              <p className="break-words text-neutral-300">{summary}</p>
              {retryAt && <p className="text-neutral-500">Retry after {Number.isNaN(Date.parse(retryAt)) ? retryAt : timeLabel(retryAt)}</p>}
            </li>;
          })}</ul>
        </div>)}
      </div>
    </div>}
  </div>;
}

export function NewsSection() {
  const [tab, setTab] = useState<"news" | "events">("news");
  const [newsDateFilter, setNewsDateFilter] = useState<"verified" | "unverified">("verified");
  const [articles, setArticles] = useState<CatalystCard[]>([]);
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [newsStatus, setNewsStatus] = useState<NewsStatus | null>(null);
  const [eventsStatus, setEventsStatus] = useState<EventStatus | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<number | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<MarketEvent | null>(null);
  const lastSeenNewsRunRef = useRef<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [newsLoadMessage, setNewsLoadMessage] = useState<string | null>(null);
  const [eventsLoadMessage, setEventsLoadMessage] = useState<string | null>(null);
  const [isRefreshingEvents, setIsRefreshingEvents] = useState(false);
  const [isRefreshingNews, setIsRefreshingNews] = useState(false);
  const [eventsRefreshMessage, setEventsRefreshMessage] = useState<string | null>(null);
  const [newsRefreshMessage, setNewsRefreshMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const getJson = async <T,>(path: string): Promise<T> => {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(path);
      return await response.json() as T;
    };
    const [newsResult, eventsResult, newsStatusResult, eventsStatusResult] = await Promise.allSettled([
      getJson<CatalystCard[]>("/api/news"),
      getJson<MarketEvent[]>("/api/events"),
      getJson<NewsStatus>("/api/news/status"),
      getJson<EventStatus>("/api/events/status"),
    ]);
    if (newsResult.status === "fulfilled") setArticles(sortedNews(newsResult.value));
    if (eventsResult.status === "fulfilled") setEvents(eventsResult.value);
    if (newsStatusResult.status === "fulfilled") {
      setNewsStatus(newsStatusResult.value);
      lastSeenNewsRunRef.current = newsStatusResult.value.lastRun?.startedAt ?? null;
    }
    if (eventsStatusResult.status === "fulfilled") setEventsStatus(eventsStatusResult.value);
    setNewsLoadMessage(newsResult.status === "rejected" || newsStatusResult.status === "rejected"
      ? "News data could not be loaded. Previous results are shown where available." : null);
    setEventsLoadMessage(eventsResult.status === "rejected" || eventsStatusResult.status === "rejected"
      ? "Events data could not be loaded. Previous results are shown where available." : null);
    setIsLoading(false);
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(initial);
  }, [load]);

  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === "visible") void load(); };
    const interval = window.setInterval(onVisible, newsStatus?.pendingSummaries ? PENDING_POLL_INTERVAL_MS : POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, newsStatus?.pendingSummaries]);

  useEffect(() => {
    const pollForCompletedRun = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const response = await fetch("/api/news/status", { cache: "no-store" });
        if (!response.ok) return;
        const status = await response.json() as NewsStatus;
        const latestRun = status.lastRun?.startedAt ?? null;
        const previousRun = lastSeenNewsRunRef.current;
        setNewsStatus(status);
        if (latestRun && previousRun && latestRun !== previousRun) {
          lastSeenNewsRunRef.current = latestRun;
          await load();
        } else if (latestRun !== previousRun) {
          lastSeenNewsRunRef.current = latestRun;
        }
      } catch {
        // The regular refresh keeps the last visible cards when status is unavailable.
      }
    };
    const interval = window.setInterval(() => void pollForCompletedRun(), RUN_COMPLETION_POLL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  async function refreshEvents() {
    setIsRefreshingEvents(true);
    setEventsRefreshMessage(null);
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
      const statusResponse = await fetch("/api/events/status", { cache: "no-store" });
      if (statusResponse.ok) setEventsStatus(await statusResponse.json() as EventStatus);
      setEventsRefreshMessage(result.failedSources.length > 0
        ? `Some event sources are unavailable: ${result.failedSources.join(", ")}.`
        : null);
    } catch (reason) {
      setEventsRefreshMessage(reason instanceof Error ? reason.message : "Could not refresh events.");
      try {
        const statusResponse = await fetch("/api/events/status", { cache: "no-store" });
        if (statusResponse.ok) setEventsStatus(await statusResponse.json() as EventStatus);
      } catch { /* Keep the refresh error visible when status is unavailable. */ }
    } finally {
      setIsRefreshingEvents(false);
    }
  }

  async function refreshNews() {
    setIsRefreshingNews(true);
    setNewsRefreshMessage(null);
    try {
      const response = await fetch("/api/news", { method: "POST", cache: "no-store" });
      if (!response.ok) {
        throw new Error(response.status === 409
          ? "News is already refreshing. Try again shortly."
          : response.status === 503
            ? "News collection is disabled."
            : "Could not refresh news from its sources.");
      }
      const result = await response.json() as NewsRefreshResult;
      const newsResponse = await fetch("/api/news", { cache: "no-store" });
      if (!newsResponse.ok) throw new Error("News was collected, but the updated list could not be loaded.");
      setArticles(sortedNews(await newsResponse.json() as CatalystCard[]));
      const statusResponse = await fetch("/api/news/status", { cache: "no-store" });
      if (statusResponse.ok) {
        const status = await statusResponse.json() as NewsStatus;
        setNewsStatus(status);
        lastSeenNewsRunRef.current = status.lastRun?.startedAt ?? null;
      }
      setNewsRefreshMessage(result.failedSources.length > 0
        ? `Some news sources are unavailable: ${result.failedSources.join(", ")}.`
        : null);
    } catch (reason) {
      setNewsRefreshMessage(reason instanceof Error ? reason.message : "Could not refresh news.");
      try {
        const statusResponse = await fetch("/api/news/status", { cache: "no-store" });
        if (statusResponse.ok) setNewsStatus(await statusResponse.json() as NewsStatus);
      } catch { /* Keep the refresh error visible when status is unavailable. */ }
    } finally {
      setIsRefreshingNews(false);
    }
  }

  const activeStatus = tab === "news" ? newsStatus : eventsStatus;
  const isRefreshing = tab === "news" ? isRefreshingNews : isRefreshingEvents;
  const refreshMessage = tab === "news" ? newsRefreshMessage : eventsRefreshMessage;
  const loadMessage = tab === "news" ? newsLoadMessage : eventsLoadMessage;
  const sourceErrors = activeStatus?.sourceErrors?.length
    ? activeStatus.sourceErrors
    : activeStatus?.failedSources.map((source) => ({ source, message: "Source unavailable" })) ?? [];
  const visibleArticles = articles.filter((article) =>
    newsDateFilter === "verified" ? article.releasedAt !== null : article.releasedAt === null,
  );
  const notices = [
    ...(loadMessage ? [loadMessage] : []),
    ...(refreshMessage && (sourceErrors.length === 0 || !refreshMessage.startsWith("Some "))
      ? [refreshMessage] : []),
  ];

  return <section id="analysis" className="flex min-h-0 min-w-0 flex-col pt-6" aria-label="News" aria-labelledby="news-heading">
    <div className="flex shrink-0 items-center justify-between gap-4">
      <h2 id="news-heading" className="text-xl font-semibold tracking-tight text-neutral-100">Analysis</h2>
      <div className="flex shrink-0 items-center gap-3">
        {tab === "news" && <button
          type="button"
          aria-label={`Showing ${newsDateFilter} news. Click to show ${newsDateFilter === "verified" ? "unverified" : "verified"} news`}
          aria-pressed={newsDateFilter === "unverified"}
          onClick={() => setNewsDateFilter((filter) => filter === "verified" ? "unverified" : "verified")}
          className={`rounded-lg border px-3 py-2 text-xs font-medium transition focus:outline-none focus:ring-2 ${newsDateFilter === "verified" ? "border-neutral-700 text-neutral-300 hover:bg-neutral-800 focus:ring-neutral-400/40" : "border-amber-700/70 bg-amber-900/30 text-amber-200 hover:bg-amber-900/50 focus:ring-amber-400/40"}`}
        >{newsDateFilter === "verified" ? "Verified" : "Unverified"}</button>}
        <CollectionErrorIndicator key={tab} section={tab} sourceErrors={sourceErrors} notices={notices} lastRun={tab === "news" ? newsStatus?.lastRun : null} />
        <button type="button" aria-label={`Refresh ${tab}`} title={`Refresh ${tab} from sources`} disabled={isRefreshing} onClick={() => void (tab === "news" ? refreshNews() : refreshEvents())} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-neutral-800 text-neutral-400 transition hover:border-neutral-600 hover:bg-neutral-800 hover:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-neutral-400/40 disabled:cursor-wait disabled:opacity-60">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={`h-5 w-5 ${isRefreshing ? "animate-spin" : ""}`}><path d="M20 11a8 8 0 0 0-14.5-4.7L3 9" /><path d="M3 4v5h5" /><path d="M4 13a8 8 0 0 0 14.5 4.7L21 15" /><path d="M16 15h5v5" /></svg>
        </button>
        <div role="tablist" aria-label="News and events" className="flex rounded-lg border border-neutral-800 p-1 text-sm">
          <button type="button" role="tab" aria-selected={tab === "news"} onClick={() => setTab("news")} className={`rounded-md px-3 py-1 ${tab === "news" ? "bg-neutral-800 text-neutral-100" : "text-neutral-400"}`}>News</button>
          <button type="button" role="tab" aria-selected={tab === "events"} onClick={() => setTab("events")} className={`rounded-md px-3 py-1 ${tab === "events" ? "bg-neutral-800 text-neutral-100" : "text-neutral-400"}`}>Events</button>
        </div>
      </div>
    </div>
    <div className="mt-2 shrink-0 text-xs text-neutral-500">
      {activeStatus?.lastSuccessfulRunAt ? `${tab === "news" ? "Last successful source" : "Last collected"} ${timeLabel(activeStatus.lastSuccessfulRunAt)}` : "Waiting for first collection"}
      {tab === "news" && newsStatus?.lastAttemptAt && <span className="ml-2">Last attempt {timeLabel(newsStatus.lastAttemptAt)}</span>}
    </div>
    {tab === "news" && newsStatus && newsStatus.pendingSummaries > 0 && <div role="status" className="mt-2 rounded-md bg-amber-400/10 px-3 py-2 text-xs text-amber-300">
      {newsStatus.pendingSummaries} source-backed {newsStatus.pendingSummaries === 1 ? "story has" : "stories have"} a summary pending. Summaries retry automatically.
      {(newsStatus.pendingSummaryIssues?.length ?? 0) > 0 && <details className="mt-1">
        <summary className="cursor-pointer">See retry status</summary>
        <ul className="mt-2 space-y-1 pl-4">{newsStatus.pendingSummaryIssues.map((issue) => <li key={issue.storyId} className="list-disc">{issue.headline}: {issue.reason}{issue.nextRetryAt ? ` · Next retry ${timeLabel(issue.nextRetryAt)}` : ""}</li>)}</ul>
      </details>}
    </div>}
    <div aria-label={tab === "news" ? "News articles" : "Upcoming events"} className="dashboard-pane-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto pr-3 pb-6">
      {isLoading ? <p className="text-sm text-neutral-500">Loading…</p> : tab === "news" ? (
        visibleArticles.length === 0 ? <p className="text-sm text-neutral-500">{articles.length === 0 ? "No watchlist catalysts collected yet." : `No ${newsDateFilter} news cards.`}</p> :
          <div className="grid grid-cols-2 gap-3">{visibleArticles.map((article) => <button key={article.id} type="button" onClick={() => setSelectedArticle(article.id)} className={`min-w-0 rounded-xl border p-4 text-left transition focus:outline-none focus:ring-2 ${article.direction === "upside" ? "border-green-700/70 bg-green-900/40 hover:border-green-500 hover:bg-green-900/55 focus:ring-green-400/40" : article.direction === "downside" ? "border-red-700/70 bg-red-900/40 hover:border-red-500 hover:bg-red-900/55 focus:ring-red-400/40" : "border-neutral-800 bg-neutral-900/50 hover:border-neutral-600 hover:bg-neutral-900 focus:ring-neutral-400/40"}`}>
            <StockBadges symbols={article.watchlistSymbols} />
            <h3 className="mt-3 text-sm font-semibold leading-5 text-neutral-100">{article.headline}</h3>
            {article.shortSummary && <p className="mt-2 line-clamp-2 text-xs leading-5 text-neutral-400">{article.shortSummary}</p>}
            <p className="mt-3 text-xs text-neutral-500">{article.releasedAt ? `Released ${releaseLabel(article.releasedAt, article.releaseDatePrecision)}` : `Publication date unverified · First found ${timeLabel(article.firstSeenAt)}`}{article.eventDate ? ` · Catalyst date ${dayLabel(article.eventDate)}` : ""} · {article.category} · {article.direction}{article.status === "pending" ? " · Summary pending" : ""}</p>
          </button>)}</div>
      ) : events.length === 0 ? <p className="text-sm text-neutral-500">No upcoming events found yet.</p> :
        <div className="grid grid-cols-2 gap-3">{events.map((event) => <button key={event.id} type="button" onClick={() => setSelectedEvent(event)} className={`min-w-0 rounded-xl border p-4 text-left transition focus:outline-none focus:ring-2 ${event.category === "earnings" ? "border-orange-700/70 bg-orange-900/60 hover:border-orange-500 hover:bg-orange-900/75 focus:ring-orange-400/40" : "border-neutral-800 bg-neutral-900/50 hover:border-neutral-600 hover:bg-neutral-900 focus:ring-neutral-400/40"}`}>
          {event.scope === "watchlist" ? <StockBadges symbols={event.watchlistSymbols} /> : <span className="text-xs font-medium text-sky-300">US market</span>}
          <h3 className="mt-3 text-sm font-semibold leading-5 text-neutral-100">{event.title}</h3>
          <p className="mt-3 text-xs text-neutral-500">{event.startsAt ? timeLabel(event.startsAt) : dayLabel(event.eventDate)} · {event.dateStatus}</p>
        </button>)}</div>}
    </div>
    {selectedArticle !== null && <NewsDetailDialog id={selectedArticle} version={articles.find((article) => article.id === selectedArticle)?.updatedAt} onClose={() => setSelectedArticle(null)} />}
    {selectedEvent && <EventDetailDialog event={selectedEvent} onClose={() => setSelectedEvent(null)} />}
  </section>;
}
