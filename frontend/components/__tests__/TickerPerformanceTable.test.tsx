// Tests for TickerPerformanceTable: verifies row rendering, the empty-state
// message, and pagination (10 rows/page) when there are more than 10 tickers.

import { fireEvent, render, screen, within } from "@testing-library/react";
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

    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("AAPL_US_EQ")).not.toBeInTheDocument();
    expect(screen.getByText(formatCurrency(47, "USD"))).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("renders an empty state when there are no closed trades", () => {
    render(<TickerPerformanceTable currency="USD" performanceByTicker={[]} />);

    expect(screen.getByText("No closed trades yet.")).toBeInTheDocument();
  });

  it("uses the dashboard P/L colours", () => {
    render(
      <TickerPerformanceTable
        currency="USD"
        performanceByTicker={[
          { ticker: "GAIN_US_EQ", realizedPnl: 47, tradeCount: 2, winRate: 0.5 },
          { ticker: "LOSS_US_EQ", realizedPnl: -12, tradeCount: 2, winRate: 0.5 },
          { ticker: "EVEN_US_EQ", realizedPnl: 0, tradeCount: 2, winRate: 0.5 },
        ]}
      />
    );

    expect(screen.getByText(formatCurrency(47, "USD"))).toHaveClass("text-[#32e64d]");
    expect(screen.getByText(formatCurrency(12, "USD"))).toHaveClass("text-[#ff3b45]");
    expect(screen.queryByText(formatCurrency(-12, "USD"))).not.toBeInTheDocument();
    expect(screen.getByText(formatCurrency(0, "USD"))).toHaveClass("text-neutral-100");
  });

  it("sorts by every column and toggles the active direction", () => {
    render(
      <TickerPerformanceTable
        currency="USD"
        performanceByTicker={[
          { ticker: "ZETA_US_EQ", realizedPnl: -10, tradeCount: 8, winRate: 0.2 },
          { ticker: "ALPHA_US_EQ", realizedPnl: 5, tradeCount: 2, winRate: 0.5 },
          { ticker: "BETA_US_EQ", realizedPnl: 20, tradeCount: 4, winRate: 0.8 },
        ]}
      />
    );

    const tickerOrder = () => screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Ticker" }));
    expect(tickerOrder()).toEqual(["ALPHA", "BETA", "ZETA"]);
    expect(screen.getByRole("columnheader", { name: "Ticker" })).toHaveAttribute("aria-sort", "ascending");

    fireEvent.click(screen.getByRole("button", { name: "Sort by Ticker" }));
    expect(tickerOrder()).toEqual(["ZETA", "BETA", "ALPHA"]);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Realized P/L" }));
    expect(tickerOrder()).toEqual(["BETA", "ALPHA", "ZETA"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Realized P/L" }));
    expect(tickerOrder()).toEqual(["ZETA", "ALPHA", "BETA"]);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Trades" }));
    expect(tickerOrder()).toEqual(["ZETA", "BETA", "ALPHA"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Trades" }));
    expect(tickerOrder()).toEqual(["ALPHA", "BETA", "ZETA"]);

    fireEvent.click(screen.getByRole("button", { name: "Sort by Win rate" }));
    expect(tickerOrder()).toEqual(["BETA", "ALPHA", "ZETA"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Win rate" }));
    expect(tickerOrder()).toEqual(["ZETA", "ALPHA", "BETA"]);
  });

  it("shows only the first 10 rows and reveals the next 10 after clicking Next", () => {
    render(<TickerPerformanceTable currency="USD" performanceByTicker={makeTickers(15)} />);

    expect(screen.getByText("TICK0")).toBeInTheDocument();
    expect(screen.getByText("TICK9")).toBeInTheDocument();
    expect(screen.queryByText("TICK10")).not.toBeInTheDocument();
    expect(screen.getByText("1–10 of 15")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("TICK10")).toBeInTheDocument();
    expect(screen.getByText("TICK14")).toBeInTheDocument();
    expect(screen.queryByText("TICK0")).not.toBeInTheDocument();
  });
});
