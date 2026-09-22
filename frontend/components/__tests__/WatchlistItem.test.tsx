import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WatchlistItem } from "../WatchlistItem";

describe("WatchlistItem", () => {
  it("visibly shades a default item while it is hovered", () => {
    const { container } = render(
      <WatchlistItem
        entry={{
          assetId: "asset-1",
          symbol: "VRT",
          name: "Vertiv Holdings Co Class A Common Stock",
          exchange: "NYSE",
          sortOrder: 0,
          addedAt: "2026-09-18T13:30:00Z",
          logoUrl: "/api/watchlist/asset-1/logo",
          quote: {
            price: null,
            previousClose: null,
            dollarChange: null,
            percentChange: null,
            sparkline: [],
            feed: "iex",
            sourceTimestamp: null,
            sourceType: null,
            freshness: "unavailable",
            isExtendedHours: false,
            isDelayed: false,
            delaySeconds: null,
          },
        }}
        mode="default"
        isDragging={false}
        isSavingOrder={false}
        onDragStart={vi.fn()}
        onDragOver={vi.fn()}
        onDrop={vi.fn()}
        onDragEnd={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(container.firstChild).toHaveClass("hover:bg-neutral-800/40");
    expect(screen.getByRole("img", { name: "Vertiv Holdings Co Class A Common Stock logo" })).toHaveAttribute(
      "src",
      "/api/watchlist/asset-1/logo",
    );
  });

  it("retries a logo when the cache version changes after an earlier load failure", () => {
    const entry = {
      assetId: "asset-1",
      symbol: "VRT",
      name: "Vertiv Holdings Co Class A Common Stock",
      exchange: "NYSE",
      sortOrder: 0,
      addedAt: "2026-09-18T13:30:00Z",
      logoUrl: "/api/watchlist/asset-1/logo",
      quote: {
        price: null,
        previousClose: null,
        dollarChange: null,
        percentChange: null,
        sparkline: [],
        feed: "iex",
        sourceTimestamp: null,
        sourceType: null,
        freshness: "unavailable" as const,
        isExtendedHours: false,
        isDelayed: false,
        delaySeconds: null,
      },
    };
    const props = {
      mode: "default" as const,
      isDragging: false,
      isSavingOrder: false,
      onDragStart: vi.fn(),
      onDragOver: vi.fn(),
      onDrop: vi.fn(),
      onDragEnd: vi.fn(),
      onRemove: vi.fn(),
    };
    const { rerender } = render(<WatchlistItem entry={entry} {...props} />);

    fireEvent.error(screen.getByRole("img", { name: "Vertiv Holdings Co Class A Common Stock logo" }));
    expect(screen.queryByRole("img", { name: "Vertiv Holdings Co Class A Common Stock logo" })).not.toBeInTheDocument();

    rerender(
      <WatchlistItem entry={{ ...entry, logoUrl: `${entry.logoUrl}?v=1` }} {...props} />,
    );

    expect(screen.getByRole("img", { name: "Vertiv Holdings Co Class A Common Stock logo" })).toHaveAttribute(
      "src",
      "/api/watchlist/asset-1/logo?v=1",
    );
  });

  it("uses an unsigned percentage beside a downward indicator", () => {
    render(
      <WatchlistItem
        entry={{
          assetId: "asset-1",
          symbol: "VRT",
          name: "Vertiv Holdings Co Class A Common Stock",
          exchange: "NYSE",
          sortOrder: 0,
          addedAt: "2026-09-18T13:30:00Z",
          logoUrl: "/api/watchlist/asset-1/logo",
          quote: {
            price: 249.22,
            previousClose: 250.42,
            dollarChange: -1.2,
            percentChange: -0.48,
            sparkline: [
              { timestamp: "2026-09-18T13:30:00Z", close: 250.42 },
              { timestamp: "2026-09-18T13:35:00Z", close: 249.22 },
            ],
            feed: "iex",
            sourceTimestamp: "2026-09-18T13:35:00Z",
            sourceType: "trade",
            freshness: "fresh",
            isExtendedHours: false,
            isDelayed: false,
            delaySeconds: null,
          },
        }}
        mode="default"
        isDragging={false}
        isSavingOrder={false}
        onDragStart={vi.fn()}
        onDragOver={vi.fn()}
        onDrop={vi.fn()}
        onDragEnd={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getByText("$249.22")).toBeInTheDocument();
    expect(screen.getByText("↘ 0.48%")).toBeInTheDocument();
    expect(screen.queryByText(/-0\.48%/)).not.toBeInTheDocument();
  });

  it("labels delayed SIP prices so they are not mistaken for live IEX data", () => {
    render(
      <WatchlistItem
        entry={{
          assetId: "asset-1",
          symbol: "VRT",
          name: "Vertiv Holdings Co Class A Common Stock",
          exchange: "NYSE",
          sortOrder: 0,
          addedAt: "2026-09-18T13:30:00Z",
          logoUrl: "/api/watchlist/asset-1/logo",
          quote: {
            price: 249.22,
            previousClose: 250.42,
            dollarChange: -1.2,
            percentChange: -0.48,
            sparkline: [],
            feed: "delayed_sip",
            sourceTimestamp: "2026-09-18T13:20:00Z",
            sourceType: "delayed_sip_trade_stream",
            freshness: "fresh",
            isExtendedHours: true,
            isDelayed: true,
            delaySeconds: 900,
          },
        }}
        mode="default"
        isDragging={false}
        isSavingOrder={false}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getByText("Delayed SIP · 15 min")).toBeInTheDocument();
  });
});
