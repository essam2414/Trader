// Tests for TradeHistoryTable: verifies row rendering (ticker, entry/exit
// price and date, quantity, P/L, holding period) and the empty-state message.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import type { Trade } from "../../lib/types";
import { TradeHistoryTable } from "../TradeHistoryTable";

const TRADE: Trade = {
  ticker: "AAPL_US_EQ",
  quantity: 10,
  entryPrice: 100,
  entryAt: "2026-01-01T10:00:00Z",
  exitPrice: 110,
  exitAt: "2026-01-05T10:00:00Z",
  pnl: 98,
  holdingPeriodHours: 96,
};

describe("TradeHistoryTable", () => {
  it("renders a row per trade with entry/exit details and P/L", () => {
    render(<TradeHistoryTable trades={[TRADE]} currency="USD" />);

    expect(screen.getByText("AAPL_US_EQ")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(100, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(110, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(98, "USD"))).toBeInTheDocument();
    expect(screen.getByText("4.0d")).toBeInTheDocument();
  });

  it("renders an empty state when there are no closed trades", () => {
    render(<TradeHistoryTable trades={[]} currency="USD" />);

    expect(screen.getByText("No closed trades yet.")).toBeInTheDocument();
  });
});
