// Tests for TickerPerformanceTable: verifies row rendering, the empty-state
// message, and pagination (10 rows/page) when there are more than 10 tickers.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import type { TickerPerformance } from "../../lib/types";
import { TickerPerformanceTable } from "../TickerPerformanceTable";

function makeTickers(count: number): TickerPerformance[] {
  return Array.from({ length: count }, (_, i) => ({
    ticker: `TICK${i}_US_EQ`,
    realizedPnl: i,
    tradeCount: 1,
    winRate: 0.5,
  }));
}

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

  it("shows only the first 10 rows and reveals the next 10 after clicking Next", () => {
    render(<TickerPerformanceTable currency="USD" performanceByTicker={makeTickers(15)} />);

    expect(screen.getByText("TICK0_US_EQ")).toBeInTheDocument();
    expect(screen.getByText("TICK9_US_EQ")).toBeInTheDocument();
    expect(screen.queryByText("TICK10_US_EQ")).not.toBeInTheDocument();
    expect(screen.getByText("1–10 of 15")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("TICK10_US_EQ")).toBeInTheDocument();
    expect(screen.getByText("TICK14_US_EQ")).toBeInTheDocument();
    expect(screen.queryByText("TICK0_US_EQ")).not.toBeInTheDocument();
  });
});
