import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WatchlistSection } from "../WatchlistSection";

describe("WatchlistSection search", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
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
  });
});
