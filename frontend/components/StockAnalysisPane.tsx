"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { AnalysisMetric, CatalystCard, StockAnalysis } from "../lib/types";
import { NewsDetailDialog } from "./NewsSection";

function timestamp(value: string | null, dateOnly = false): string {
  if (!value || Number.isNaN(Date.parse(value))) return "Unavailable";
  return new Intl.DateTimeFormat("en-GB", dateOnly
    ? { day: "numeric", month: "short", year: "numeric", timeZone: "America/New_York" }
    : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" },
  ).format(new Date(value));
}

function useVisibleData<T>(url: string, validate: (value: T) => boolean, pending?: (value: T) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;
    const load = async () => {
      clearTimeout(timer);
      if (document.visibilityState === "hidden") return;
      controller?.abort();
      const request = new AbortController();
      controller = request;
      let delay = 30_000;
      try {
        const response = await fetch(url, { cache: "no-store", signal: request.signal });
        if (!response.ok) throw new Error("Unavailable");
        const result = await response.json() as T;
        if (!validate(result)) throw new Error("Invalid response");
        if (!stopped && !request.signal.aborted) {
          setData(result);
          setError(false);
          if (pending?.(result)) delay = 2_000;
        }
      } catch {
        if (!stopped && !request.signal.aborted) setError(true);
      } finally {
        if (!stopped && !request.signal.aborted) timer = setTimeout(() => void load(), delay);
      }
    };
    const visible = () => {
      if (document.visibilityState === "visible") void load();
      else { clearTimeout(timer); controller?.abort(); }
    };
    void load();
    document.addEventListener("visibilitychange", visible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", visible);
    };
  }, [url, validate, pending]);
  return { data, error };
}

function validAnalysis(value: StockAnalysis) { return Array.isArray(value?.metrics); }
function pendingAnalysis(value: StockAnalysis) { return value.status === "loading"; }
function validNews(value: CatalystCard[]) { return Array.isArray(value); }

function valueLabel(metric: AnalysisMetric): string {
  if (metric.value === null || !Number.isFinite(metric.value)) return "—";
  const value = metric.value;
  if (metric.unit === "usd") return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
  if (metric.unit === "points") return `${value > 0 ? "+" : ""}${value.toFixed(2)} pp`;
  if (metric.unit === "percent") return `${value.toFixed(2)}%`;
  if (metric.id === "extension") return `${value > 0 ? "+" : ""}${value.toFixed(2)} ATR`;
  if (metric.unit === "ratio") return `${value.toFixed(2)}×`;
  return value.toFixed(1);
}

function MetricRow({ metric }: { metric: AnalysisMetric }) {
  const [open, setOpen] = useState(false);
  const infoId = useId();
  const button = useRef<HTMLButtonElement>(null);
  return <div className="border-b border-neutral-800/70 py-3 last:border-b-0">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-neutral-300">{metric.label}</span>
          <button ref={button} type="button" aria-label={`About ${metric.label}`} aria-expanded={open}
            aria-controls={infoId} onClick={() => setOpen((current) => !current)}
            onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-neutral-500 transition hover:bg-neutral-800 hover:text-white focus-visible:outline-2 focus-visible:outline-neutral-400">
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" className="h-3.5 w-3.5">
              <circle cx="10" cy="10" r="7.25" /><path strokeLinecap="round" d="M10 9v5M10 6v.5" />
            </svg>
          </button>
        </div>
        <p className="mt-0.5 text-[11px] text-neutral-500">{metric.interpretation}</p>
      </div>
      <span data-testid={`metric-${metric.id}`} className={`shrink-0 pt-0.5 text-sm font-semibold tabular-nums ${metric.value === null || !Number.isFinite(metric.value) ? "text-neutral-500" : metric.condition === "supportive" ? "text-[#32e64d]" : metric.condition === "caution" ? "text-[#ff4b55]" : "text-white"}`}>
        {valueLabel(metric)}
      </span>
    </div>
    {metric.detail && <p className="mt-1 text-[11px] leading-4 text-neutral-500">{metric.detail}</p>}
    {open && <div id={infoId} role="region" aria-label={`${metric.label} explanation`} tabIndex={-1}
      onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); button.current?.focus(); } }}
      className="mt-2 space-y-2 rounded-lg border border-neutral-700 bg-neutral-900 p-3 text-xs leading-5 text-neutral-300">
      <p>{metric.description}</p><p>{metric.relevance}</p><p>{metric.thresholds}</p>
      <button type="button" onClick={() => { setOpen(false); button.current?.focus(); }}
        className="rounded px-1 text-neutral-400 underline underline-offset-2 hover:text-white">Close explanation</button>
    </div>}
  </div>;
}

function Analysis({ assetId }: { assetId: string }) {
  const { data, error } = useVisibleData<StockAnalysis>(
    `/api/watchlist/${encodeURIComponent(assetId)}/analysis`, validAnalysis, pendingAnalysis,
  );
  return <>
    <div className="shrink-0 space-y-1 border-b border-neutral-800/70 pb-3 text-[11px] leading-5 text-neutral-500">
      <p className="text-xs text-neutral-400">Swing outlook · 2–10 trading days</p>
      {data?.dailyAsOf && <p>Daily signals · close {timestamp(data.dailyAsOf, true)}</p>}
      {data?.intradayAsOf && <p>Price &amp; volume · {timestamp(data.intradayAsOf)} · delayed</p>}
      {data?.metrics.length ? <p>Green: bullish · Red: bearish · White: neutral</p> : null}
    </div>
    <div className="dashboard-pane-scrollbar min-h-0 flex-1 overflow-y-auto pr-2">
      {error && <p role="status" className="py-3 text-xs leading-5 text-neutral-400">Analysis could not be refreshed. {data?.metrics.length ? "Previous readings are shown." : "Retrying shortly."}</p>}
      {!data && !error && <p role="status" className="py-5 text-sm text-neutral-500">Loading analysis…</p>}
      {data?.message && <p role="status" className="py-3 text-xs leading-5 text-neutral-400">{data.status === "stale" ? "Stale readings · " : ""}{data.message}</p>}
      {data?.metrics.map((metric) => <MetricRow key={metric.id} metric={metric} />)}
      {!!data?.metrics.length && <p className="pt-3 text-[10px] leading-4 text-neutral-600">Daily signals update after the close. Price context updates every 5 minutes with data about 15–20 minutes behind the market. Conditions describe the setup, not a forecast.</p>}
    </div>
  </>;
}

function NewsPage({ assetId, page, onPage }: { assetId: string; page: number; onPage: (page: number) => void }) {
  const query = new URLSearchParams({ assetId, limit: "21", offset: String(page * 20) });
  const { data, error } = useVisibleData<CatalystCard[]>(`/api/news?${query}`, validNews);
  const [selected, setSelected] = useState<number | null>(null);
  const closeDetail = useCallback(() => setSelected(null), []);
  const articles = [...new Map((data ?? []).slice(0, 20).map((item) => [item.id, item])).values()];
  return <>
    <p className="mb-3 shrink-0 text-xs leading-5 text-neutral-500">Stories linked to this stock by your news pipeline.</p>
    <div className="dashboard-pane-scrollbar min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-2">
      {error && <p role="status" className="text-xs leading-5 text-neutral-400">News could not be refreshed. {data ? "Previous stories are shown." : "Retrying shortly."}</p>}
      {!data && !error && <p role="status" className="py-3 text-sm text-neutral-500">Loading stock news…</p>}
      {data && articles.length === 0 && <p className="py-3 text-sm text-neutral-500">{page ? "No older stories for this stock." : "No news has been linked to this stock yet."}</p>}
      {articles.map((article) => <button type="button" key={article.id} onClick={() => setSelected(article.id)}
        className="block w-full rounded-xl border border-neutral-800 bg-neutral-900/35 p-3.5 text-left transition hover:border-neutral-600 hover:bg-neutral-900 focus-visible:outline-2 focus-visible:outline-neutral-400">
        <div className="mb-2 flex flex-wrap gap-1">
          {article.watchlistSymbols.map((symbol) => <span key={symbol} className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium text-neutral-400">{symbol}</span>)}
        </div>
        <h3 className="text-sm font-medium leading-5 text-neutral-100">{article.headline}</h3>
        {article.shortSummary && <p className="mt-2 line-clamp-3 text-xs leading-5 text-neutral-400">{article.shortSummary}</p>}
        <p className="mt-2 text-[10px] leading-4 text-neutral-500">
          {article.releasedAt ? timestamp(article.releasedAt, article.releaseDatePrecision === "date") : "Publication date unverified"}
          {" · "}{article.category.replaceAll("_", " ")}
          {article.status === "pending" ? " · Summary pending" : ""}
        </p>
      </button>)}
    </div>
    {(page > 0 || (data?.length ?? 0) > 20) && <div className="mt-3 flex shrink-0 items-center justify-between border-t border-neutral-800 pt-3 text-xs text-neutral-400">
      <button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className="rounded px-2 py-1 hover:text-white disabled:opacity-30">Newer stories</button>
      <span>Page {page + 1}</span>
      <button type="button" disabled={(data?.length ?? 0) <= 20} onClick={() => onPage(page + 1)} className="rounded px-2 py-1 hover:text-white disabled:opacity-30">Older stories</button>
    </div>}
    {selected !== null && <NewsDetailDialog key={selected} id={selected} version={articles.find((item) => item.id === selected)?.updatedAt} onClose={closeDetail} />}
  </>;
}

export function StockAnalysisPane({ assetId }: { assetId: string }) {
  const [tab, setTab] = useState<"analysis" | "news">("analysis");
  const [page, setPage] = useState(0);
  const id = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  return <aside aria-label="Stock analysis" className="mt-8 flex h-[480px] min-w-0 flex-col border-t border-neutral-800/80 pt-6 lg:mt-0 lg:border-t-0 lg:border-l lg:pl-8 lg:pt-5">
    <div role="tablist" aria-label="Stock analysis and news" className="mb-4 flex w-fit shrink-0 rounded-lg border border-neutral-800 p-1 text-sm">
      {(["analysis", "news"] as const).map((name, index) => <button key={name} ref={(node) => { tabRefs.current[index] = node; }}
        type="button" role="tab" id={`${id}-${name}`} aria-controls={`${id}-panel`} aria-selected={tab === name}
        tabIndex={tab === name ? 0 : -1} onClick={() => setTab(name)} onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
          setTab(next === 0 ? "analysis" : "news");
          tabRefs.current[next]?.focus();
        }} className={`rounded-md px-4 py-1.5 transition focus-visible:outline-2 focus-visible:outline-neutral-400 ${tab === name ? "bg-neutral-800 text-white" : "text-neutral-500 hover:text-neutral-200"}`}>
        {name === "analysis" ? "Analysis" : "News"}
      </button>)}
    </div>
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`} className="flex min-h-0 flex-1 flex-col">
      {tab === "analysis" ? <Analysis key={assetId} assetId={assetId} /> : <NewsPage key={`${assetId}-${page}`} assetId={assetId} page={page} onPage={setPage} />}
    </div>
  </aside>;
}
