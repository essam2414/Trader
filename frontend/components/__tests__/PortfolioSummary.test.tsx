// Tests for PortfolioSummary: verifies it renders the account's total value, cash, and P/L figures.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { PortfolioSummary } from "../PortfolioSummary";

describe("PortfolioSummary", () => {
  it("renders only realized P/L", () => {
    render(
      <PortfolioSummary
        account={{
          id: 1,
          currency: "USD",
          totalValue: 10250.5,
          cash: { availableToTrade: 500, inPies: 0, reservedForOrders: 0 },
          unrealizedProfitLoss: 750.5,
          realizedProfitLoss: 120,
          weeklyRealizedProfitLoss: 0,
        }}
      />
    );

    expect(screen.getByText(formatCurrency(120, "USD"))).toBeInTheDocument();
    expect(screen.queryByText("Total value")).not.toBeInTheDocument();
    expect(screen.queryByText("Cash available")).not.toBeInTheDocument();
    expect(screen.queryByText("Unrealized P/L")).not.toBeInTheDocument();
  });

  it("shows an unsigned realized loss while retaining its loss colour", () => {
    render(
      <PortfolioSummary
        account={{
          id: 1,
          currency: "USD",
          totalValue: 10250.5,
          cash: { availableToTrade: 500, inPies: 0, reservedForOrders: 0 },
          unrealizedProfitLoss: -750.5,
          realizedProfitLoss: -120,
          weeklyRealizedProfitLoss: 0,
        }}
      />
    );

    expect(screen.getByText(formatCurrency(120, "USD"))).toHaveClass("text-[#ff3b45]");
    expect(screen.queryByText(formatCurrency(-120, "USD"))).not.toBeInTheDocument();
  });
});
