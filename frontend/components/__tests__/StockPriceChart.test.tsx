import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatAxisPrice, mergeDisplayBars, StockPriceChart } from "../StockPriceChart";
import type { StockChart, WatchlistEntry } from "../../lib/types";

const chart: StockChart = {
  assetId: "asset-now",
  symbol: "NOW",
  name: "ServiceNow, Inc.",
  range: "1D",
  intervalSeconds: 900,
  canonicalFeed: "sip",
  adjustment: "raw",
  canonicalThrough: "2026-09-23T14:30:00Z",
  delaySeconds: 900,
  canonicalBars: [bar("2026-09-23T14:00:00Z", 136), bar("2026-09-23T14:15:00Z", 137)],
  provisionalIexBars: [bar("2026-09-23T14:15:00Z", 137.25), bar("2026-09-23T14:30:00Z", 138)],
};

function bar(startsAt: string, close: number) {
  return { startsAt, open: close - 0.2, high: close + 0.4, low: close - 0.5, close, volume: 10, session: "regular" as const };
}

function watchlistEntry(price = 140.25, previousClose = 137): WatchlistEntry {
  return {
    assetId: "asset-now", symbol: "NOW", name: "ServiceNow, Inc.", exchange: "NYSE", sortOrder: 0,
    addedAt: "2026-09-23T13:00:00Z", logoUrl: "/api/watchlist/asset-now/logo",
    quote: { price, previousClose, dollarChange: price - previousClose, percentChange: ((price - previousClose) / previousClose) * 100, sparkline: [], feed: "iex", sourceTimestamp: "2026-09-23T14:30:00Z", sourceType: "iex_trade_stream", freshness: "fresh", isExtendedHours: false, isDelayed: false, delaySeconds: null },
  };
}

class FakeEventSource {
  static sources: FakeEventSource[] = [];
  private listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  constructor(readonly url: string) { FakeEventSource.sources.push(this); }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) { this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]); }
  close() {}
  emit(type: string, data: unknown) { for (const listener of this.listeners.get(type) ?? []) listener({ data: JSON.stringify(data) } as MessageEvent<string>); }
}

describe("StockPriceChart", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); FakeEventSource.sources = []; });

  it("renders the compact header, current price, positive movement, and every bottom range", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve({ ok: true, json: async () => input === "/api/watchlist" ? [watchlistEntry()] : chart })));
    render(<StockPriceChart assetId="asset-now" />);

    expect(await screen.findByRole("heading", { name: "ServiceNow" })).toBeInTheDocument();
    expect(screen.getByText("NOW · NYSE")).toBeInTheDocument();
    expect(screen.getByTestId("stock-current-price")).toHaveTextContent("$140.25");
    expect(screen.getByText("↗ 3.25 (2.37%) today")).toHaveClass("text-[#32e64d]");
    for (const range of ["1D", "1W", "1M", "3M", "1Y", "MAX"]) expect(screen.getByRole("button", { name: range })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1D" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/Raw SIP|SIP history|IEX tail|partial-market|15 min delayed|SIP close/i)).not.toBeInTheDocument();
  });

  it("requests each range without removing the stable stock information", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = vi.fn((input: string) => Promise.resolve({ ok: true, json: async () => input === "/api/watchlist" ? [watchlistEntry()] : { ...chart, range: input.split("range=")[1] } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<StockPriceChart assetId="asset-now" />);
    await waitFor(() => expect(screen.getByTestId("stock-current-price")).toHaveTextContent("$140.25"));
    for (const range of ["1W", "1M", "3M", "1Y", "MAX"]) {
      fireEvent.click(screen.getByRole("button", { name: range }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/watchlist/asset-now/chart?range=${range}`, expect.anything()));
      expect(screen.getByRole("button", { name: range })).toHaveAttribute("aria-pressed", "true");
    }
    expect(screen.getByRole("heading", { name: "ServiceNow" })).toBeInTheDocument();
  });

  it("uses negative daily movement and updates the latest price from a live trade", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve({ ok: true, json: async () => input === "/api/watchlist" ? [watchlistEntry(135, 137)] : chart })));
    render(<StockPriceChart assetId="asset-now" />);
    expect(await screen.findByText("↘ 2.00 (1.46%) today")).toHaveClass("text-[#ff4b55]");
    FakeEventSource.sources[0].emit("trade", { price: 141.5, timestamp: "2026-09-23T14:31:00Z" });
    await waitFor(() => expect(screen.getByTestId("stock-current-price")).toHaveTextContent("$141.50"));
    expect(screen.getByText("↗ 4.50 (3.28%) today")).toHaveClass("text-[#32e64d]");
  });

  it("renders a neutral zero daily change from the unchanged previous close", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve({ ok: true, json: async () => input === "/api/watchlist" ? [watchlistEntry(137, 137)] : chart })));
    render(<StockPriceChart assetId="asset-now" />);

    expect(await screen.findByText("0.00 (0.00%) today")).toHaveClass("text-neutral-500");
  });

  it("shows an understated failure state", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve(input === "/api/watchlist" ? { ok: true, json: async () => [watchlistEntry()] } : { ok: false, json: async () => ({}) })));
    render(<StockPriceChart assetId="asset-now" />);
    expect(await screen.findByText("Price history unavailable.")).toBeInTheDocument();
  });

  it("shows the open-position level when price history is unavailable", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve(
      input.endsWith("/position")
        ? { ok: true, json: async () => ({ purchasePrice: 62.75, purchasePriceCurrency: "USD" }) }
        : input === "/api/watchlist"
          ? { ok: true, json: async () => [watchlistEntry()] }
          : { ok: false, json: async () => ({}) },
    )));
    render(<StockPriceChart assetId="asset-now" />);

    expect(await screen.findByTestId("purchase-price-line")).toHaveAttribute("aria-label", "Average purchase price $62.75");
    expect(screen.getByTestId("purchase-price-line")).toHaveClass("border-dashed");
  });

  it("keeps the purchase level across ranges and live price updates", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve({ ok: true, json: async () =>
      input.endsWith("/position")
        ? { purchasePrice: 1744.51, purchasePriceCurrency: "USD" }
        : input === "/api/watchlist"
          ? [watchlistEntry()]
          : { ...chart, range: input.split("range=")[1] },
    })));
    render(<StockPriceChart assetId="asset-now" />);

    const line = await screen.findByTestId("purchase-price-line");
    expect(line).toHaveAttribute("aria-label", "Average purchase price $1,744.51");
    expect(Number.parseFloat(line.style.top)).toBeGreaterThan(0);
    expect(Number.parseFloat(line.style.top)).toBeLessThan(100);
    fireEvent.click(screen.getByRole("button", { name: "1W" }));
    FakeEventSource.sources[0].emit("trade", { price: 150 });
    await waitFor(() => expect(screen.getByTestId("stock-current-price")).toHaveTextContent("$150.00"));
    expect(screen.getByTestId("purchase-price-line")).toHaveAttribute("aria-label", "Average purchase price $1,744.51");
  });

  it("keeps the purchase level when the overnight chart has no bars or quote", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn((input: string) => Promise.resolve({ ok: true, json: async () =>
      input.endsWith("/position")
        ? { purchasePrice: 62.75, purchasePriceCurrency: "USD" }
        : input === "/api/watchlist"
          ? [{ ...watchlistEntry(), quote: { ...watchlistEntry().quote, price: null } }]
          : { ...chart, canonicalBars: [], provisionalIexBars: [] },
    })));
    render(<StockPriceChart assetId="asset-now" />);

    expect(await screen.findByTestId("purchase-price-line")).toHaveAttribute("aria-label", "Average purchase price $62.75");
    expect(screen.getByText("Price history unavailable.")).toBeInTheDocument();
  });
});

describe("chart price labels", () => {
  it("rounds axis values to three significant figures", () => {
    expect(formatAxisPrice(123.456)).toBe("123");
    expect(formatAxisPrice(1234.56)).toBe("1,230");
    expect(formatAxisPrice(0.012345)).toBe("0.0123");
  });
});

describe("mergeDisplayBars", () => {
  it("returns one chronologically sorted series with provisional and live bars replacing matching timestamps", () => {
    const result = mergeDisplayBars(chart, [bar("2026-09-23T14:30:00Z", 139), bar("2026-09-23T14:45:00Z", 140)]);
    expect(result.map((point) => point.startsAt)).toEqual(["2026-09-23T14:00:00Z", "2026-09-23T14:15:00Z", "2026-09-23T14:30:00Z", "2026-09-23T14:45:00Z"]);
    expect(result.map((point) => point.close)).toEqual([136, 137.25, 139, 140]);
  });

  it("preserves the server-produced 15-minute chart points without further sampling", () => {
    const canonicalBars = Array.from({ length: 4 }, (_, index) =>
      bar(`2026-09-23T14:${String(index * 15).padStart(2, "0")}:00Z`, 100 + index),
    );

    const result = mergeDisplayBars({ ...chart, canonicalBars, provisionalIexBars: [] });

    expect(result).toHaveLength(4);
    expect(result.map((point) => point.startsAt)).toEqual(canonicalBars.map((point) => point.startsAt));
    expect(result.map((point) => point.close)).toEqual(canonicalBars.map((point) => point.close));
  });

  it("deduplicates only an exact SIP/IEX fifteen-minute timestamp", () => {
    const canonicalBars = Array.from({ length: 4 }, (_, index) =>
      bar(`2026-09-23T14:${String(index * 15).padStart(2, "0")}:00Z`, 100 + index),
    );
    const result = mergeDisplayBars({
      ...chart,
      canonicalBars,
      provisionalIexBars: [bar("2026-09-23T14:15:00Z", 999)],
    });

    expect(result).toHaveLength(4);
    expect(result[1].startsAt).toBe("2026-09-23T14:15:00Z");
    expect(result[1].close).toBe(999);
    expect(result.map((point) => point.startsAt)).toEqual(canonicalBars.map((point) => point.startsAt));
  });

  it("replaces the latest live fifteen-minute bar while retaining history", () => {
    const canonicalBars = Array.from({ length: 4 }, (_, index) =>
      bar(`2026-09-23T14:${String(index * 15).padStart(2, "0")}:00Z`, 100 + index),
    );
    const result = mergeDisplayBars(
      { ...chart, canonicalBars, provisionalIexBars: [] },
      [bar("2026-09-23T14:45:00Z", 250)],
    );

    expect(result).toHaveLength(4);
    expect(result.slice(0, 3).map((point) => point.close)).toEqual(canonicalBars.slice(0, 3).map((point) => point.close));
    expect(result.at(-1)?.close).toBe(250);
  });
});
