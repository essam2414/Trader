import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CatalystCard } from "../../lib/types";
import { NewsSection } from "../NewsSection";

const card: CatalystCard = {
  id: 7,
  headline: "Acme wins supply agreement",
  shortSummary: "Acme announced a supply agreement.",
  watchlistSymbols: ["ACME"],
  category: "deal",
  direction: "upside",
  status: "ready",
  releasedAt: "2026-09-24T20:00:00Z",
  firstSeenAt: "2026-09-24T20:30:00Z",
  updatedAt: "2026-09-24T20:30:00Z",
};

const event = {
  id: "earnings:acme:2026-09-30",
  title: "Acme earnings report",
  category: "earnings",
  scope: "watchlist",
  eventDate: "2026-10-21",
  previousEventDate: "2026-10-20",
  startsAt: null,
  timePrecision: "date_only",
  dateStatus: "changed",
  watchlistSymbols: ["ACME"],
  sourceUrl: "https://example.com/calendar",
  lastVerifiedAt: "2026-09-25T06:00:00Z",
};

function response(data: unknown, ok = true) {
  return { ok, json: async () => data };
}

function stubBriefing(news: CatalystCard[] = [card], events = [event], failedEvents = false) {
  const fetchMock = vi.fn(async (path: string) => {
    if (path === "/api/news") return response(news);
    if (path === "/api/events") return response(events, !failedEvents);
    if (path === "/api/news/status") return response({
      lastSuccessfulRunAt: "2026-09-25T08:55:00Z", lastAttemptAt: "2026-09-25T09:00:00Z",
      lastRun: { startedAt: "2026-09-25T09:00:00Z", attempted: 2, succeeded: 1, failed: 1, skipped: 0, newSourceItems: 2, newCards: 1 },
      failedSources: ["sec"],
      sourceErrors: [{ source: "sec", message: "HTTP 503 Service Unavailable" }], pendingSummaries: 0,
    });
    if (path === "/api/events/status") return response({
      lastSuccessfulRunAt: "2026-09-24T07:00:00Z", failedSources: [], sourceErrors: [], pendingSummaries: 0,
    });
    if (path === "/api/news/7") return response({
      ...card,
      detailSummary: "Acme announced an agreement; financial terms were not disclosed.",
      relevanceReason: "Acme is a watched stock.",
      keyFacts: ["Agreement announced"],
      unknowns: ["Financial terms"],
      sources: [{
        title: "Official announcement", provider: "company", url: "https://example.com/release",
        publishedAt: "2026-09-24T20:00:00Z",
        dateStatus: "verified",
      }],
    });
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("NewsSection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("explains why possible duplicates are waiting outside the feed", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [],
        pendingSummaries: 2, unresolvedDevelopments: 2, pendingSummaryIssues: [],
      });
      if (path === "/api/events/status") return response({ lastSuccessfulRunAt: null, sourceErrors: [] });
      return response([]);
    }));
    render(<NewsSection />);
    expect(await screen.findByText(/2 possible developments are being checked against earlier coverage/)).toBeInTheDocument();
  });

  it("colors upside and downside news cards while leaving unclear cards neutral", async () => {
    stubBriefing([
      card,
      { ...card, id: 8, headline: "Acme cuts guidance", direction: "downside" },
      { ...card, id: 9, headline: "Acme announces review", direction: "unclear" },
    ]);
    render(<NewsSection />);

    expect(await screen.findByRole("button", { name: /Acme wins supply agreement/i })).toHaveClass("bg-green-900/40");
    expect(screen.getByRole("button", { name: /Acme cuts guidance/i })).toHaveClass("bg-red-900/40");
    expect(screen.getByRole("button", { name: /Acme announces review/i })).toHaveClass("bg-neutral-900/50");
  });

  it("keeps undated discoveries out of the verified feed until its filter is changed", async () => {
    stubBriefing([
      { ...card, id: 8, headline: "Undated analyst report", releasedAt: null,
        firstSeenAt: "2026-09-27T14:27:00Z" },
      { ...card, headline: "Dated analyst report", releasedAt: "2026-09-22T11:39:00Z" },
    ]);
    render(<NewsSection />);

    expect(await screen.findByRole("button", { name: /Dated analyst report/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Undated analyst report/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Showing verified news/ }));
    expect(screen.getByRole("button", { name: /Undated analyst report/i })).toHaveTextContent("Publication date unverified");
    expect(screen.queryByRole("button", { name: /\bDated analyst report/i })).not.toBeInTheDocument();
  });

  it("shows one card per story, watched symbols, source detail, and partial source status", async () => {
    stubBriefing([card, { ...card }]);
    render(<NewsSection />);

    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    const cards = await screen.findAllByRole("button", { name: /Acme wins supply agreement/i });
    expect(cards).toHaveLength(1);
    expect(within(cards[0]).getByText("ACME")).toBeInTheDocument();
    expect(screen.queryByText(/Coverage incomplete/)).not.toBeInTheDocument();
    const warning = screen.getByRole("button", { name: "News collection errors" });
    expect(screen.queryByRole("dialog", { name: "News collection errors" })).not.toBeInTheDocument();
    fireEvent.mouseEnter(warning);
    expect(screen.getByRole("dialog", { name: "News collection errors" })).toHaveTextContent("SEC filings");
    fireEvent.mouseLeave(warning.parentElement!);
    expect(screen.queryByRole("dialog", { name: "News collection errors" })).not.toBeInTheDocument();
    fireEvent.click(warning);
    const errors = screen.getByRole("dialog", { name: "News collection errors" });
    expect(within(errors).getByText(/1 source has an unresolved error/)).toBeInTheDocument();
    expect(within(errors).getByText("SEC filings")).toBeInTheDocument();
    expect(within(errors).getByText("HTTP 503 Service Unavailable")).toBeInTheDocument();
    expect(within(errors).getByText(/Last run: 1 succeeded · 1 failed · 0 deferred/)).toBeInTheDocument();
    expect(within(errors).getByText(/2 new source items · 1 new card/)).toBeInTheDocument();
    fireEvent.mouseLeave(warning.parentElement!);
    expect(errors).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByRole("heading", { name: "Analysis" }));
    expect(screen.queryByRole("dialog", { name: "News collection errors" })).not.toBeInTheDocument();
    expect(screen.getByText(/Last successful source/)).toBeInTheDocument();
    expect(screen.queryByText(/Last run: 1 succeeded · 1 failed · 0 deferred/)).not.toBeInTheDocument();
    fireEvent.click(cards[0]);

    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText(/financial terms were not disclosed/)).toBeInTheDocument();
    expect(within(dialog).getByText("Agreement announced")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Official announcement" })).toHaveAttribute(
      "href", "https://example.com/release",
    );
  });

  it("switches to dated events and shows a changed date in the detail", async () => {
    stubBriefing([card], [
      event,
      { ...event, id: "fed:decision:2026-10-21", title: "FOMC policy decision", category: "fomc", scope: "us_market", watchlistSymbols: [] },
    ]);
    render(<NewsSection />);
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));

    const eventCard = await screen.findByRole("button", { name: /Acme earnings report/i });
    expect(within(eventCard).getByText("ACME")).toBeInTheDocument();
    expect(eventCard).toHaveClass("bg-orange-900/60");
    expect(screen.getByRole("button", { name: /FOMC policy decision/i })).toHaveClass("bg-neutral-900/50");
    fireEvent.click(eventCard);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Previously scheduled for/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /View schedule source/ })).toHaveAttribute(
      "href", "https://example.com/calendar",
    );
  });

  it("refreshes event sources and reloads the Events tab", async () => {
    let refreshed = false;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/events" && init?.method === "POST") {
        refreshed = true;
        return response({ refreshedSources: 3, refreshedEvents: 1, failedSources: [] });
      }
      if (path === "/api/events") {
        return response(refreshed ? [{ ...event, title: "Updated earnings date" }] : [event]);
      }
      if (path === "/api/news") return response([card]);
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], pendingSummaries: 0,
      });
      if (path === "/api/events/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], pendingSummaries: 0,
      });
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewsSection />);

    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh events" }));

    expect(screen.queryByText(/Refreshing events from their sources/)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Updated earnings date/i })).toBeInTheDocument();
    expect(screen.queryByText(/Events refreshed from/)).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Events" })).toHaveAttribute("aria-selected", "true");
    expect(fetchMock).toHaveBeenCalledWith("/api/events", { method: "POST", cache: "no-store" });
  });

  it("keeps each tab's collection time and refresh cycle independent", async () => {
    let finishEvents!: (value: ReturnType<typeof response>) => void;
    let finishNews!: (value: ReturnType<typeof response>) => void;
    const eventsRefresh = new Promise<ReturnType<typeof response>>((resolve) => { finishEvents = resolve; });
    const newsRefresh = new Promise<ReturnType<typeof response>>((resolve) => { finishNews = resolve; });
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/events" && init?.method === "POST") return eventsRefresh;
      if (path === "/api/news" && init?.method === "POST") return newsRefresh;
      if (path === "/api/events/status") return Promise.resolve(response({
        lastSuccessfulRunAt: "2026-09-24T07:00:00Z", failedSources: [], pendingSummaries: 0,
      }));
      if (path === "/api/news/status") return Promise.resolve(response({
        lastSuccessfulRunAt: "2026-09-25T08:55:00Z", failedSources: [], pendingSummaries: 0,
      }));
      return Promise.resolve(response(path === "/api/events" ? [event] : [card]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewsSection />);
    expect(await screen.findByText(/Last successful source 25 Sept 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(screen.getByText(/Last collected 24 Sept 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh events" }));
    expect(screen.getByRole("button", { name: "Refresh events" })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    const newsButton = screen.getByRole("button", { name: "Refresh news" });
    expect(newsButton).not.toBeDisabled();
    expect(newsButton.querySelector("svg")).not.toHaveClass("animate-spin");
    fireEvent.click(newsButton);
    expect(newsButton).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(screen.getByRole("button", { name: "Refresh events" })).toBeDisabled();
    finishEvents(response({ refreshedSources: 1, refreshedEvents: 1, failedSources: [] }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh events" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.getByRole("button", { name: "Refresh news" })).toBeDisabled();
    finishNews(response({ refreshedSources: 1, refreshedStories: 1, failedSources: [] }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh news" })).not.toBeDisabled());
    expect(fetchMock).toHaveBeenCalledWith("/api/events", { method: "POST", cache: "no-store" });
    expect(fetchMock).toHaveBeenCalledWith("/api/news", { method: "POST", cache: "no-store" });
  });

  it("keeps news usable when the events endpoint fails and marks summaries pending", async () => {
    stubBriefing([{ ...card, status: "pending", shortSummary: "" }], [], true);
    render(<NewsSection />);

    expect(await screen.findByRole("button", { name: /Acme wins supply agreement/i })).toBeInTheDocument();
    expect(screen.getByText(/Summary pending/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "News collection errors" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    const warning = screen.getByRole("button", { name: "Events collection errors" });
    fireEvent.click(warning);
    expect(screen.getByRole("dialog", { name: "Events collection errors" })).toHaveTextContent("Events data could not be loaded");
  });

  it("shows the active tab's source error details and hides the icon when that tab is healthy", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [], pendingSummaries: 0,
      });
      if (path === "/api/events/status") return response({
        lastSuccessfulRunAt: null, failedSources: ["events:fed"],
        sourceErrors: [{ source: "events:fed", message: "Provider timed out" }],
      });
      return response(path === "/api/events" ? [event] : [card]);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewsSection />);
    await screen.findByRole("button", { name: /Acme wins supply agreement/i });
    expect(screen.queryByRole("button", { name: "News collection errors" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    const warning = screen.getByRole("button", { name: "Events collection errors" });
    fireEvent.click(warning);
    expect(screen.getByRole("dialog", { name: "Events collection errors" })).toHaveTextContent("Provider timed out");
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.queryByRole("button", { name: "News collection errors" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Events collection errors" })).not.toBeInTheDocument();
  });

  it("shows a source failure immediately after a manual refresh fails", async () => {
    let failed = false;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/events" && init?.method === "POST") {
        failed = true;
        return response(null, false);
      }
      if (path === "/api/events/status") return response({
        lastSuccessfulRunAt: null,
        failedSources: failed ? ["events:fed"] : [],
        sourceErrors: failed ? [{ source: "events:fed", message: "HTTP 503 Service Unavailable" }] : [],
      });
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [], pendingSummaries: 0,
      });
      return response(path === "/api/events" ? [event] : [card]);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewsSection />);
    await screen.findByRole("button", { name: /Acme wins supply agreement/i });
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(screen.queryByRole("button", { name: "Events collection errors" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh events" }));
    const warning = await screen.findByRole("button", { name: "Events collection errors" });
    fireEvent.click(warning);
    expect(screen.getByRole("dialog", { name: "Events collection errors" })).toHaveTextContent("HTTP 503 Service Unavailable");
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.queryByRole("button", { name: "News collection errors" })).not.toBeInTheDocument();
  });

  it("shows deferred job counts only inside the popup even without a source error", async () => {
    const fetchMock = stubBriefing();
    fetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/news") return response([card]);
      if (path === "/api/events") return response([event]);
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: "2026-09-27T20:30:00Z", lastAttemptAt: "2026-09-27T20:30:00Z",
        lastRun: { startedAt: "2026-09-27T20:30:00Z", attempted: 2, succeeded: 2, failed: 0, skipped: 1 },
        failedSources: [], sourceErrors: [], pendingSummaries: 0,
      });
      if (path === "/api/events/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [], pendingSummaries: 0,
      });
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<NewsSection />);

    const warning = await screen.findByRole("button", { name: "News collection errors" });
    expect(screen.queryByText(/Last run: 2 succeeded/)).not.toBeInTheDocument();
    fireEvent.mouseEnter(warning);
    expect(within(screen.getByRole("dialog", { name: "News collection errors" }))
      .getByText(/Last run: 2 succeeded · 0 failed · 1 deferred/)).toBeInTheDocument();
  });

  it("groups many source errors in a scrollable popup that stays open until dismissed", async () => {
    const sourceErrors = [
      ...["BE", "CRDO", "MRVL", "MU", "VRT", "WDC"].map((symbol) => ({
        source: `openai_web:${symbol}`, message: "OpenAI web search incomplete: max_output_tokens",
      })),
      { source: "rss:ir_be", message: "Client error '403 Forbidden' for url '[source URL]'\nFor more information check: [source URL]; retry after 2026-09-28T17:14:00Z" },
      { source: "rss:prnewswire", message: "Client error '404 Not Found' for url '[source URL]'" },
      { source: "gdelt:NOW", message: "Client error '429 Too Many Requests' for url '[source URL]'" },
    ];
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: sourceErrors.map((error) => error.source),
        sourceErrors, pendingSummaries: 0,
      });
      if (path === "/api/events/status") return response({ lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [] });
      return response(path === "/api/events" ? [] : [card]);
    }));
    render(<NewsSection />);
    const warning = await screen.findByRole("button", { name: "News collection errors" });
    fireEvent.click(warning);

    const popup = screen.getByRole("dialog", { name: "News collection errors" });
    expect(within(popup).getByText(/9 sources have unresolved errors/)).toBeInTheDocument();
    expect(within(popup).getByRole("heading", { name: /OpenAI web search/ })).toBeInTheDocument();
    expect(within(popup).getByRole("heading", { name: /RSS feeds/ })).toBeInTheDocument();
    expect(within(popup).getByRole("heading", { name: /GDELT/ })).toBeInTheDocument();
    expect(within(popup).getByText("Bloom Energy")).toBeInTheDocument();
    expect(within(popup).getByText("403 Forbidden")).toBeInTheDocument();
    expect(within(popup).queryByText(/For more information check/)).not.toBeInTheDocument();
    const scroller = within(popup).getByRole("region", { name: "Error details" });
    expect(scroller).toHaveClass("overflow-y-auto", "collection-error-scrollbar");
    expect(scroller).not.toHaveClass("focus:ring-2");
    fireEvent.scroll(scroller);
    fireEvent.pointerDown(scroller);
    expect(popup).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "News collection errors" })).not.toBeInTheDocument();
  });

  it("updates pending cards, the pending count, and open details without a manual refresh", async () => {
    vi.useFakeTimers();
    let completed = false;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") throw new Error("Unexpected source refresh");
      if (path === "/api/news") return response([{
        ...card,
        status: completed ? "ready" : "pending",
        shortSummary: completed ? "New AI summary" : "",
        updatedAt: completed ? "2026-09-27T15:30:00Z" : card.updatedAt,
      }]);
      if (path === "/api/news/status") return response({
        lastSuccessfulRunAt: null, failedSources: [], sourceErrors: [], pendingSummaries: completed ? 0 : 1,
        pendingSummaryIssues: completed ? [] : [{
          storyId: 7, headline: card.headline, reason: "AI response did not complete",
          nextRetryAt: "2026-09-27T16:00:00Z",
        }],
      });
      if (path === "/api/news/7") return response({
        ...card, status: completed ? "ready" : "pending",
        detailSummary: completed ? "New AI detail" : "",
        relevanceReason: "", keyFacts: [], unknowns: [],
        sources: [],
      });
      if (path === "/api/events") return response([]);
      if (path === "/api/events/status") return response({ lastSuccessfulRunAt: null, failedSources: [] });
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<NewsSection />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByText(/1 source-backed story has a summary pending/)).toBeInTheDocument();
      fireEvent.click(screen.getByText("See retry status"));
      expect(screen.getByText(/AI response did not complete/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Acme wins supply agreement/i }));
      await act(async () => { await Promise.resolve(); });
      expect(within(screen.getByRole("dialog")).getByText(/AI summary pending/)).toBeInTheDocument();

      completed = true;
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(screen.queryByText(/source-backed story has a summary pending/)).not.toBeInTheDocument();
      expect(screen.getByText("New AI summary")).toBeInTheDocument();
      expect(within(screen.getByRole("dialog")).getByText("New AI detail")).toBeInTheDocument();
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
