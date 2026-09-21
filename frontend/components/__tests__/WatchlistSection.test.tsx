import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WatchlistSection } from "../WatchlistSection";

describe("WatchlistSection search", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "elementFromPoint");
  });

  it("closes an open search panel when the user clicks away", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
    render(<WatchlistSection />);

    fireEvent.change(screen.getByRole("combobox", { name: /search us equities/i }), {
      target: { value: "AAPL" },
    });
    expect(screen.getByText("Searching…")).toBeInTheDocument();

    fireEvent.pointerDown(document.body);

    expect(screen.queryByText("Searching…")).not.toBeInTheDocument();
  });

  it("renders watchlist quotes as a compact list rather than a table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            assetId: "asset-1",
            symbol: "NOW",
            name: "ServiceNow Inc Common Stock",
            exchange: "NASDAQ",
            sortOrder: 0,
            addedAt: "2026-09-18T13:30:00Z",
            logoUrl: "/api/watchlist/asset-1/logo",
            quote: {
              price: 136.01,
              previousClose: 135.47,
              dollarChange: 0.54,
              percentChange: 0.4,
              sparkline: [
                { timestamp: "2026-09-18T13:30:00Z", close: 135.47 },
                { timestamp: "2026-09-18T13:35:00Z", close: 136.01 },
              ],
              feed: "iex",
              sourceTimestamp: "2026-09-18T13:35:00Z",
              sourceType: "trade",
              freshness: "fresh",
              isExtendedHours: false,
            },
          },
        ],
      }),
    );

    const { container } = render(<WatchlistSection />);

    expect(await screen.findByText("ServiceNow")).toBeInTheDocument();
    expect(screen.getByText("↗ 0.40%")).toBeInTheDocument();
    expect(screen.getByText("$136.01")).toBeInTheDocument();
    expect(container.querySelector("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Regular session")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Watchlist entries")).toHaveClass("overflow-y-auto");
    expect(screen.getByLabelText("Watchlist")).toHaveClass("flex-col");
  });

  it("moves the dragged row itself while the other rows reorder", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => watchlistEntries() });
    vi.stubGlobal("fetch", fetchMock);
    render(<WatchlistSection />);

    await screen.findByText("Apple");
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    const apple = screen.getByText("Apple").closest("[data-watchlist-entry]");
    const microsoft = screen.getByText("Microsoft").closest("[data-watchlist-entry]");
    expect(apple).not.toBeNull();
    expect(microsoft).not.toBeNull();

    vi.spyOn(apple!, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 320,
      height: 68,
    } as DOMRect);
    Object.defineProperty(apple!, "setPointerCapture", { configurable: true, value: vi.fn() });
    Object.defineProperty(document, "elementFromPoint", {
      configurable: true,
      value: () => microsoft,
    });

    fireEvent.pointerDown(apple!, { pointerId: 1, clientX: 20, clientY: 10 });
    await waitFor(() => expect(apple).toHaveStyle({ position: "fixed" }));
    expect(apple).toHaveAttribute("draggable", "false");

    fireEvent.pointerMove(apple!, { pointerId: 1, clientX: 40, clientY: 100 });

    await waitFor(() => expect(entryIds()).toEqual(["msft", "aapl"]));
    expect(apple).toHaveStyle({ left: "0px" });

    fireEvent.pointerUp(window, { pointerId: 1 });
    await waitFor(() => expect(apple).not.toHaveStyle({ position: "fixed" }));
    expect(fetchMock).toHaveBeenLastCalledWith("/api/watchlist/order", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetIds: ["msft", "aapl"] }),
    });
  });
});

function entryIds() {
  return [...document.querySelectorAll<HTMLElement>("[data-watchlist-entry]")]
    .map((entry) => entry.dataset.watchlistEntry);
}

function watchlistEntries() {
  return [
    watchlistEntry("aapl", "AAPL", "Apple Inc Common Stock", 188.25),
    watchlistEntry("msft", "MSFT", "Microsoft Corp Common Stock", 420.34),
  ];
}

function watchlistEntry(assetId: string, symbol: string, name: string, price: number) {
  return {
    assetId,
    symbol,
    name,
    exchange: "NASDAQ",
    sortOrder: 0,
    addedAt: "2026-09-18T13:30:00Z",
    logoUrl: `/api/watchlist/${assetId}/logo`,
    quote: {
      price,
      previousClose: price - 1,
      dollarChange: 1,
      percentChange: 0.5,
      sparkline: [],
      feed: "iex",
      sourceTimestamp: "2026-09-18T13:35:00Z",
      sourceType: "trade",
      freshness: "fresh",
      isExtendedHours: false,
    },
  };
}
