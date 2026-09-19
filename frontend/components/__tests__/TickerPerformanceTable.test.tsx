// Tests for TickerPerformanceTable: verifies row rendering and the empty-state message.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { TickerPerformanceTable } from "../TickerPerformanceTable";

describe("TickerPerformanceTable", () => {
  it("renders a row per ticker", () => {
    render(
      <TickerPerformanceTable
        currency="USD"
        performanceByTicker={[{ ticker: "AAPL_US_EQ", realizedPnl: 47, tradeCount: 2, winRate: 0.5 }]}
      />
    );

    expect(screen.getByText("AAPL_US_EQ")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(47, "USD"))).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("renders an empty state when there are no closed trades", () => {
    render(<TickerPerformanceTable currency="USD" performanceByTicker={[]} />);

    expect(screen.getByText("No closed trades yet.")).toBeInTheDocument();
  });
});
