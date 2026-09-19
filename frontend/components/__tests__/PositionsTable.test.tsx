// Tests for PositionsTable: verifies row rendering, per-position currency
// formatting for price columns, and the empty-state message.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { PositionsTable } from "../PositionsTable";

describe("PositionsTable", () => {
  it("renders a row per position", () => {
    render(
      <PositionsTable
        currency="USD"
        positions={[
          {
            ticker: "NVDA_US_EQ",
            name: "NVIDIA Corp",
            currency: "USD",
            quantity: 10,
            averagePricePaid: 120.5,
            currentPrice: 135.2,
            currentValue: 1352,
            unrealizedProfitLoss: 147,
          },
        ]}
      />
    );

    expect(screen.getByText("NVDA_US_EQ")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(135.2, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(147, "USD"))).toBeInTheDocument();
  });

  it("formats price columns using the position's own currency and value columns using the account currency", () => {
    render(
      <PositionsTable
        currency="USD"
        positions={[
          {
            ticker: "VOD_LSE_EQ",
            name: "Vodafone Group",
            currency: "GBP",
            quantity: 5,
            averagePricePaid: 80,
            currentPrice: 90,
            currentValue: 450,
            unrealizedProfitLoss: 50,
          },
        ]}
      />
    );

    expect(screen.getByText(formatCurrency(80, "GBP"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(90, "GBP"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(450, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(50, "USD"))).toBeInTheDocument();
  });

  it("renders an empty state when there are no positions", () => {
    render(<PositionsTable currency="USD" positions={[]} />);

    expect(screen.getByText("No open positions.")).toBeInTheDocument();
  });
});
