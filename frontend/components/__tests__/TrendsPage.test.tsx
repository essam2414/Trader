import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TrendsPage, moveSelectedAsset, readSavedTrends } from "../TrendsPage";
import type { ChartRange, WatchlistEntry } from "../../lib/types";

vi.mock("../StockPriceChart", () => ({
  StockPriceChart: ({ assetId, range, compact, live, purchasePriceOverride }: { assetId: string; range: ChartRange; compact: boolean; live?: { latestPrice: number | null }; purchasePriceOverride: number | null }) =>
    <div data-testid="trend-chart" data-asset-id={assetId} data-range={range} data-compact={compact} data-live-price={live?.latestPrice ?? ""} data-purchase-price={purchasePriceOverride ?? ""} />,
}));

const entries = [entry("asset-aapl", "AAPL"), entry("asset-msft", "MSFT"), entry("asset-now", "NOW")];

function entry(assetId: string, symbol: string): WatchlistEntry {
  return {
    assetId, symbol, name: `${symbol} Incorporated`, exchange: "NASDAQ", sortOrder: 0,
    addedAt: "2026-09-25T12:00:00Z", logoUrl: `/api/watchlist/${assetId}/logo`,
    quote: {
      price: 100, previousClose: 99, dollarChange: 1, percentChange: 1, sparkline: [],
      feed: "iex", sourceTimestamp: null, sourceType: null, freshness: "fresh",
      isExtendedHours: false, isDelayed: false, delaySeconds: null,
    },
  };
}

class FakeEventSource {
  static sources: FakeEventSource[] = [];
  closed = false;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  constructor(readonly url: string) { FakeEventSource.sources.push(this); }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) { this.listeners.set(type, listener); }
  emit(type: string, data: unknown) { this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent<string>); }
  close() { this.closed = true; }
}

describe("TrendsPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    FakeEventSource.sources = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ({
      ok: true,
      json: async () => input === "/api/watchlist/positions"
        ? { "asset-aapl": { purchasePrice: 150.25, purchasePriceCurrency: "USD" } }
        : entries,
    })));
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("selects watchlist stocks and applies one range to all charts", async () => {
    render(<TrendsPage />);
    expect(screen.getByRole("main")).toHaveClass("font-sans");
    expect(await screen.findByText("No charts selected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "1D" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1W" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Add stocks" }));
    const picker = document.getElementById("trends-stock-picker")!;
    expect(within(picker).getAllByRole("checkbox")).toHaveLength(3);
    fireEvent.click(within(picker).getByRole("checkbox", { name: /AAPL/ }));
    fireEvent.click(within(picker).getByRole("checkbox", { name: /MSFT/ }));
    fireEvent.click(screen.getByRole("button", { name: "3M" }));

    await waitFor(() => expect(screen.getAllByTestId("trend-chart")).toHaveLength(2));
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.range)).toEqual(["3M", "3M"]);
    expect(screen.getAllByTestId("trend-chart").every((chart) => chart.dataset.compact === "true")).toBe(true);
    await waitFor(() => expect(FakeEventSource.sources.at(-1)?.url).toBe(
      "/api/watchlist/charts/stream?assetIds=asset-aapl%2Casset-msft",
    ));
    expect(FakeEventSource.sources.filter((source) => !source.closed)).toHaveLength(1);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/watchlist/positions", expect.anything());
    await waitFor(() => expect(screen.getAllByTestId("trend-chart")[0]).toHaveAttribute("data-purchase-price", "150.25"));
    FakeEventSource.sources.at(-1)!.emit("trade", { symbol: "AAPL", price: 123.45 });
    await waitFor(() => expect(screen.getAllByTestId("trend-chart")[0]).toHaveAttribute("data-live-price", "123.45"));
    expect(screen.getAllByTestId("trend-chart")[1]).toHaveAttribute("data-live-price", "");
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("trader.trends.v1")!)).toEqual({
      assetIds: ["asset-aapl", "asset-msft"], range: "3M",
    }));
  });

  it("restores saved charts, reorders them with the keyboard, and removes only the chart", async () => {
    window.localStorage.setItem("trader.trends.v1", JSON.stringify({
      assetIds: ["asset-aapl", "deleted-asset", "asset-msft"], range: "1W",
    }));
    const fetchMock = vi.mocked(fetch);
    render(<TrendsPage />);
    await waitFor(() => expect(screen.getAllByTestId("trend-chart")).toHaveLength(2));
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-aapl", "asset-msft"]);
    expect(screen.getByRole("button", { name: "1W" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Reorder" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Move AAPL chart" }), { key: "ArrowRight" });
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-msft", "asset-aapl"]);
    expect(FakeEventSource.sources.filter((source) => !source.closed)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove AAPL chart" }));
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-msft"]);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("asset-aapl"), expect.objectContaining({ method: "DELETE" }));
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("trader.trends.v1")!).assetIds).toEqual(["asset-msft"]));
  });

  it("ranks only on a Trend click and saves the returned order", async () => {
    window.localStorage.setItem("trader.trends.v1", JSON.stringify({ assetIds: ["asset-aapl", "asset-msft"], range: "1W" }));
    const fetchMock = vi.fn(async (input: string) => ({
      ok: true,
      json: async () => input.startsWith("/api/watchlist/trends?")
        ? [
          { assetId: "asset-msft", symbol: "MSFT", status: "ready", score: 82, weekTrendPercent: 4, monthRecoveryPercent: 12, risingSessions: 3, asOf: "2026-09-25T19:30:00Z" },
          { assetId: "asset-aapl", symbol: "AAPL", status: "ready", score: 51, weekTrendPercent: 2, monthRecoveryPercent: 5, risingSessions: 2, asOf: "2026-09-25T19:30:00Z" },
        ]
        : input === "/api/watchlist/positions" ? {} : entries,
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TrendsPage />);
    await waitFor(() => expect(screen.getAllByTestId("trend-chart")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "1M" }));
    expect(fetchMock.mock.calls.some(([url]) => url.startsWith("/api/watchlist/trends?"))).toBe(false);
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-aapl", "asset-msft"]);

    fireEvent.click(screen.getByRole("button", { name: "Trend" }));
    await waitFor(() => expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-msft", "asset-aapl"]));
    expect(fetchMock.mock.calls.filter(([url]) => url.startsWith("/api/watchlist/trends?"))).toHaveLength(1);
    expect(screen.getByText("Trend #1 · 82/100")).toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("trader.trends.v1")!).assetIds).toEqual(["asset-msft", "asset-aapl"]));
  });

  it("keeps chart order when trend history cannot be loaded", async () => {
    window.localStorage.setItem("trader.trends.v1", JSON.stringify({ assetIds: ["asset-aapl", "asset-msft"], range: "1W" }));
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ({
      ok: !input.startsWith("/api/watchlist/trends?"),
      json: async () => input === "/api/watchlist/positions" ? {} : entries,
    })));
    render(<TrendsPage />);
    await waitFor(() => expect(screen.getAllByTestId("trend-chart")).toHaveLength(2));

    fireEvent.click(screen.getByRole("button", { name: "Trend" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your chart order was kept");
    expect(screen.getAllByTestId("trend-chart").map((chart) => chart.dataset.assetId)).toEqual(["asset-aapl", "asset-msft"]);
  });
});

describe("saved Trends preferences", () => {
  it("rejects invalid data and deduplicates saved selection", () => {
    expect(readSavedTrends("invalid")).toEqual({ assetIds: [], range: "1W" });
    expect(readSavedTrends(JSON.stringify({ assetIds: ["a", "a", 1, "b"], range: "wrong" })))
      .toEqual({ assetIds: ["a", "b"], range: "1W" });
    expect(readSavedTrends(JSON.stringify({ assetIds: ["a"], range: "1D" })))
      .toEqual({ assetIds: ["a"], range: "1W" });
    expect(moveSelectedAsset(["a", "b", "c"], "a", "c")).toEqual(["b", "c", "a"]);
  });
});
