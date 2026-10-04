import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StockAnalysisPane } from "../StockAnalysisPane";
import type { AnalysisMetric, CatalystCard, StockAnalysis } from "../../lib/types";

function metric(overrides: Partial<AnalysisMetric> = {}): AnalysisMetric {
  return { id: "rsi14", label: "RSI · 14 days", value: 74.2, unit: "number", basis: "daily", condition: "supportive",
    interpretation: "Upward momentum · overbought", detail: "", description: "RSI measures recent gains and losses.",
    relevance: "Helps judge momentum.", thresholds: "Above 70 is stretched, but can remain strong.", ...overrides };
}
function analysis(overrides: Partial<StockAnalysis> = {}): StockAnalysis {
  return { assetId: "asset-sndk", symbol: "SNDK", status: "ready", dailyAsOf: "2026-10-02T20:00:00Z",
    intradayAsOf: "2026-10-05T15:30:00Z", calculatedAt: "2026-10-05T15:45:00Z", nextRefreshAt: "2026-10-05T15:50:00Z",
    delaySeconds: 900, historySessions: 250, message: null, metrics: [metric(), metric({ id: "atr14", label: "Daily range · ATR14",
      value: 3.15, unit: "usd", condition: "neutral", interpretation: "Volatility" }),
      metric({ id: "range_low", label: "Prior 20-session low", value: 90, unit: "usd", condition: "caution", interpretation: "Below support" })], ...overrides };
}
function story(id: number): CatalystCard {
  return { id, headline: `Sandisk development ${id}`, shortSummary: "Company update", watchlistSymbols: ["SNDK"],
    category: "earnings", direction: "unclear", status: "pending", releasedAt: null, releaseDatePrecision: null,
    eventDate: null, firstSeenAt: "2026-10-05T14:00:00Z", updatedAt: "2026-10-05T14:00:00Z" };
}
const response = (value: unknown) => Promise.resolve({ ok: true, json: async () => value });

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("stock analysis pane", () => {
  it("shows bullish numbers in green, bearish numbers in red and neutral numbers in white, with accessible explanations", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(analysis())));
    render(<StockAnalysisPane assetId="asset-sndk" />);
    expect(await screen.findByTestId("metric-rsi14")).toHaveClass("text-[#32e64d]");
    expect(screen.getByTestId("metric-range_low")).toHaveClass("text-[#ff4b55]");
    expect(screen.getByTestId("metric-atr14")).toHaveClass("text-white");
    expect(screen.getByText(/Green: bullish/)).toHaveTextContent("Red: bearish");
    expect(screen.getByText(/Daily signals · close/)).toBeInTheDocument();
    expect(screen.getByText(/Price & volume/)).toHaveTextContent("delayed");
    const info = screen.getByRole("button", { name: "About RSI · 14 days" });
    fireEvent.click(info);
    expect(screen.getByRole("region", { name: "RSI · 14 days explanation" })).toHaveTextContent("Above 70");
    expect(info).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(info, { key: "Escape" });
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    fireEvent.click(info);
    fireEvent.click(screen.getByRole("button", { name: "Close explanation" }));
    expect(info).toHaveFocus();
  });

  it("loads stock news only when selected and paginates using the same asset filter", async () => {
    const fetchMock = vi.fn((url: string) => response(url.includes("/analysis") ? analysis()
      : url.includes("offset=20") ? [story(21)] : Array.from({ length: 21 }, (_, i) => story(i + 1))));
    vi.stubGlobal("fetch", fetchMock);
    render(<StockAnalysisPane assetId="asset-sndk" />);
    await screen.findByTestId("metric-rsi14");
    expect(fetchMock.mock.calls.every(([url]) => !url.includes("/news"))).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(await screen.findByText("Sandisk development 1")).toBeInTheDocument();
    expect(screen.getAllByText(/Publication date unverified/)).toHaveLength(20);
    expect(screen.getByRole("tab", { name: "News" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: "Older stories" }));
    expect(await screen.findByText("Sandisk development 21")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/news?assetId=asset-sndk&limit=21&offset=20", expect.anything());
    expect(screen.queryByText("Sandisk development 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Newer stories" })).toBeEnabled();
  });

  it("opens existing sourced news details and supports keyboard tab switching", async () => {
    const fetchMock = vi.fn((url: string) => response(url.includes("/analysis") ? analysis()
      : url === "/api/news/1" ? { ...story(1), detailSummary: "", relevanceReason: "", keyFacts: [], unknowns: [],
        sources: [{ provider: "Company", title: "Original release", url: "https://example.com/release", publishedAt: null, dateStatus: "unverified" }] }
      : [story(1)]));
    vi.stubGlobal("fetch", fetchMock);
    render(<StockAnalysisPane assetId="asset-sndk" />);
    fireEvent.keyDown(screen.getByRole("tab", { name: "Analysis" }), { key: "ArrowRight" });
    fireEvent.click(await screen.findByText("Sandisk development 1"));
    expect(await screen.findByRole("link", { name: "Original release" })).toHaveAttribute("href", "https://example.com/release");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not carry metrics to another stock and represents missing data explicitly", async () => {
    const fetchMock = vi.fn((url: string) => response(url.includes("asset-sndk") ? analysis() : analysis({ assetId: "asset-msft", symbol: "MSFT",
      status: "partial", metrics: [metric({ value: null, condition: "unavailable", interpretation: "Unavailable" })], message: "More history needed." })));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<StockAnalysisPane key="asset-sndk" assetId="asset-sndk" />);
    await screen.findByText("74.2");
    view.rerender(<StockAnalysisPane key="asset-msft" assetId="asset-msft" />);
    expect(screen.queryByText("74.2")).not.toBeInTheDocument();
    expect(await screen.findByTestId("metric-rsi14")).toHaveTextContent("—");
    expect(screen.getByText("More history needed.")).toBeInTheDocument();
  });

  it("distinguishes a failed news request from an empty feed", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => url.includes("/analysis") ? response(analysis()) : Promise.reject(new Error("offline"))));
    render(<StockAnalysisPane assetId="asset-sndk" />);
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("News could not be refreshed"));
    expect(screen.queryByText(/No news has been linked/)).not.toBeInTheDocument();
  });

  it("polls visible news every thirty seconds and stops when hidden or unmounted", async () => {
    vi.useFakeTimers();
    let visibility = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility as DocumentVisibilityState);
    const fetchMock = vi.fn((url: string) => response(url.includes("/analysis") ? analysis() : [story(1)]));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<StockAnalysisPane assetId="asset-sndk" />);
    fireEvent.click(screen.getByRole("tab", { name: "News" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(fetchMock.mock.calls.filter(([url]) => url.includes("/news?"))).toHaveLength(2);
    visibility = "hidden";
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetchMock.mock.calls.filter(([url]) => url.includes("/news?"))).toHaveLength(2);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("retains readings with an explicit stale notice", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(analysis({ status: "stale", message: "Market data unavailable. Retrying shortly." }))));
    render(<StockAnalysisPane assetId="asset-sndk" />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Stale readings"));
    expect(screen.getByTestId("metric-rsi14")).toHaveTextContent("74.2");
  });
});
