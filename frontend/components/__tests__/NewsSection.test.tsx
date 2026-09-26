import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewsSection } from "../NewsSection";

const card = {
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

function stubBriefing(news = [card], events = [event], failedEvents = false) {
  const fetchMock = vi.fn(async (path: string) => {
    if (path === "/api/news") return response(news);
    if (path === "/api/events") return response(events, !failedEvents);
    if (path === "/api/news/status") return response({
      lastSuccessfulRunAt: "2026-09-25T08:55:00Z", failedSources: ["sec"],
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
      }],
    });
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("NewsSection", () => {
  afterEach(() => vi.unstubAllGlobals());

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

  it("shows one card per story, watched symbols, source detail, and partial source status", async () => {
    stubBriefing([card, { ...card }]);
    render(<NewsSection />);

    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    const cards = await screen.findAllByRole("button", { name: /Acme wins supply agreement/i });
    expect(cards).toHaveLength(1);
    expect(within(cards[0]).getByText("ACME")).toBeInTheDocument();
    expect(screen.queryByText(/Some sources are unavailable/)).not.toBeInTheDocument();
    const warning = screen.getByRole("button", { name: "News collection errors" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(warning);
    expect(within(screen.getByRole("tooltip")).getByText("sec: HTTP 503 Service Unavailable")).toBeInTheDocument();
    fireEvent.mouseLeave(warning.parentElement!);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    expect(screen.getByText(/Last collected/)).toBeInTheDocument();
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
    expect(await screen.findByText(/Last collected 25 Sept 2026/)).toBeInTheDocument();
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
    fireEvent.focus(warning);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Events data could not be loaded");
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
    fireEvent.mouseEnter(warning);
    expect(screen.getByRole("tooltip")).toHaveTextContent("events:fed: Provider timed out");
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.queryByRole("button", { name: "News collection errors" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
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
    fireEvent.mouseEnter(warning);
    expect(screen.getByRole("tooltip")).toHaveTextContent("events:fed: HTTP 503 Service Unavailable");
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.queryByRole("button", { name: "News collection errors" })).not.toBeInTheDocument();
  });
});
