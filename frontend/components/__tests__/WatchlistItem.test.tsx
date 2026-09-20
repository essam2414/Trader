import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WatchlistItem } from "../WatchlistItem";

describe("WatchlistItem", () => {
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
});
