import { fireEvent, render, screen, within } from "@testing-library/react";
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
      lastSuccessfulRunAt: "2026-09-25T08:55:00Z", failedSources: ["sec"], pendingSummaries: 0,
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

  it("shows one card per story, watched symbols, source detail, and partial source status", async () => {
    stubBriefing([card, { ...card }]);
    render(<NewsSection />);

    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    const cards = await screen.findAllByRole("button", { name: /Acme wins supply agreement/i });
    expect(cards).toHaveLength(1);
    expect(within(cards[0]).getByText("ACME")).toBeInTheDocument();
    expect(screen.getByText(/Some sources are unavailable: sec/)).toBeInTheDocument();
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
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewsSection />);

    fireEvent.click(screen.getByRole("button", { name: "Refresh events" }));

    expect(screen.queryByText(/Refreshing events from their sources/)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Updated earnings date/i })).toBeInTheDocument();
    expect(screen.queryByText(/Events refreshed from/)).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Events" })).toHaveAttribute("aria-selected", "true");
    expect(fetchMock).toHaveBeenCalledWith("/api/events", { method: "POST", cache: "no-store" });
  });

  it("keeps news usable when the events endpoint fails and marks summaries pending", async () => {
    stubBriefing([{ ...card, status: "pending", shortSummary: "" }], [], true);
    render(<NewsSection />);

    expect(await screen.findByRole("button", { name: /Acme wins supply agreement/i })).toBeInTheDocument();
    expect(screen.getByText(/Summary pending/)).toBeInTheDocument();
    expect(screen.getByText(/Some briefing data is unavailable/)).toBeInTheDocument();
  });
});
