// Tests for PerformanceMetrics: verifies it renders realized P/L, win rate,
// expectancy, drawdown, and cash drag, and shows a placeholder for ratios
// that are undefined when there are no closed trades.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import type { PortfolioMetrics } from "../../lib/types";
import { PerformanceMetrics } from "../PerformanceMetrics";

const METRICS: PortfolioMetrics = {
  realizedPnl: 57,
  trading212RealizedPnl: 57,
  winRate: 0.6666666666666666,
  averageWinningTrade: 54,
  averageLosingTrade: -51,
  expectancy: 19,
  profitFactor: 2.12,
  payoffRatio: 1.06,
  averageHoldingPeriodHours: 56,
  bestTradePnl: 98,
  worstTradePnl: -51,
  currentStreak: -1,
  longestWinStreak: 2,
  longestLossStreak: 1,
  closedTradeCount: 3,
  performanceByTicker: [],
  entriesByDayOfWeek: {},
  exitsByDayOfWeek: {},
  entriesByHourOfDay: {},
  exitsByHourOfDay: {},
  maxDrawdown: 0.25,
  cashDrag: 0.1,
  dividendIncome: 10,
  dividendIncomeByTicker: {},
};

describe("PerformanceMetrics", () => {
  it("renders realized P/L, win rate, expectancy, drawdown, and cash drag", () => {
    render(<PerformanceMetrics metrics={METRICS} currency="USD" />);

    expect(screen.getByText(formatCurrency(57, "USD"))).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(19, "USD"))).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText("10.0%")).toBeInTheDocument();
  });

  it("shows a placeholder dash for profit factor and payoff ratio when there are no closed trades", () => {
    render(
      <PerformanceMetrics
        metrics={{ ...METRICS, closedTradeCount: 0, winRate: 0, profitFactor: null, payoffRatio: null }}
        currency="USD"
      />
    );

    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });
});
