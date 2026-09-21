"use client";

import { useCallback, useEffect, useState } from "react";
import type { NewsArticle } from "../lib/types";

const POLL_INTERVAL_MS = 5 * 60_000;

function timeLabel(timestamp: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

function orderedUniqueArticles(articles: NewsArticle[]): NewsArticle[] {
  const articlesById = new Map<number, NewsArticle>();
  for (const article of articles) {
    const existing = articlesById.get(article.id);
    if (!existing || Date.parse(article.updatedAt) > Date.parse(existing.updatedAt)) {
      articlesById.set(article.id, article);
    }
  }
  return [...articlesById.values()].sort(
    (left, right) =>
      Date.parse(right.updatedAt) - Date.parse(left.updatedAt) || right.id - left.id,
  );
}

function valueLabel(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2) ?? "—";
}

function NewsDetailDialog({ article, onClose }: { article: NewsArticle; onClose: () => void }) {
  const fields = Object.entries(article.rawData).sort(([left], [right]) => left.localeCompare(right));

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <button
        type="button"
        aria-label="Close news detail"
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="news-detail-heading"
        className="relative z-10 flex max-h-[calc(100vh-3rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/70"
      >
        <div className="flex items-start justify-between gap-5 border-b border-neutral-800 px-6 py-5">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-neutral-500">Alpaca news detail</p>
            <h3 id="news-detail-heading" className="mt-1 text-lg font-semibold text-neutral-100">{article.headline}</h3>
          </div>
          <button type="button" aria-label="Close news detail" onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xl text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100">×</button>
        </div>
        <dl className="grid gap-px overflow-y-auto bg-neutral-800 p-px sm:grid-cols-2">
          {fields.map(([name, value]) => (
            <div key={name} className="min-w-0 bg-neutral-950 px-5 py-4">
              <dt className="text-xs font-medium uppercase tracking-wider text-neutral-500">{name}</dt>
              <dd className="mt-1 whitespace-pre-wrap break-words font-mono text-xs leading-5 text-neutral-200">{valueLabel(value)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

export function NewsSection() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const loadNews = useCallback(async () => {
    try {
      const response = await fetch("/api/news", { cache: "no-store" });
      const body: unknown = await response.json();
      if (!response.ok) {
        setMessage(typeof body === "object" && body && "detail" in body ? String(body.detail) : "News unavailable");
        return;
      }
      setArticles(orderedUniqueArticles(body as NewsArticle[]));
      setMessage(null);
    } catch {
      setMessage("News unavailable");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadNews(), 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadNews();
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadNews]);

  return (
    <section className="flex min-h-0 min-w-0 flex-col pt-6" aria-labelledby="news-heading">
      <div className="shrink-0 flex items-baseline justify-between gap-4">
        <h2 id="news-heading" className="text-xl font-semibold tracking-tight text-neutral-100">News</h2>
      </div>
      <div aria-label="News articles" className="dashboard-pane-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto pr-3 pb-6">
        {message && <p role="status" className="rounded-md bg-amber-400/10 px-3 py-2 text-sm text-amber-300">{message}</p>}
      {isLoading ? <p className="mt-4 text-sm text-neutral-500">Loading news…</p> : articles.length === 0 && !message ? <p className="mt-4 text-sm text-neutral-500">Add equities to your watchlist to see their related news.</p> : (
        <div className="mt-4 grid grid-cols-2 gap-3">
          {articles.map((article) => (
            <button
              key={article.id}
              type="button"
              onClick={() => setSelectedArticle(article)}
              className="min-w-0 rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 text-left transition hover:border-neutral-600 hover:bg-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-400/40"
            >
              <div className="flex flex-wrap gap-1.5">
                {article.watchlistSymbols.map((symbol) => <span key={symbol} className="rounded-md bg-neutral-800 px-1.5 py-0.5 font-mono text-[11px] font-medium text-neutral-300">{symbol}</span>)}
              </div>
              <h3 className="mt-3 text-sm font-semibold leading-5 text-neutral-100">{article.headline}</h3>
              <p className="mt-2 text-xs text-neutral-500">Last updated {timeLabel(article.updatedAt)}</p>
            </button>
          ))}
        </div>
      )}
      </div>
      {selectedArticle && <NewsDetailDialog article={selectedArticle} onClose={() => setSelectedArticle(null)} />}
    </section>
  );
}
