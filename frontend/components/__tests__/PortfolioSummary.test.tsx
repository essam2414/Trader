// Tests for PortfolioSummary: verifies it renders the account's total value, cash, and P/L figures.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { PortfolioSummary } from "../PortfolioSummary";

describe("PortfolioSummary", () => {
  it("stacks realized P/L with the cumulative good and bad trade totals", () => {
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
        totalWinningTradePnl={250}
        totalLosingTradePnl={75}
      />
    );

    expect(screen.getByText(formatCurrency(120, "USD"))).toBeInTheDocument();
    expect(screen.getByText("Good trades")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(250, "USD"))).toHaveClass("text-[#32e64d]");
    expect(screen.getByText("Bad trades")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(75, "USD"))).toHaveClass("text-[#ff3b45]");
    expect(screen.getByLabelText("Trade outcome summary")).toHaveClass("flex-col");
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
        totalWinningTradePnl={0}
        totalLosingTradePnl={120}
      />
    );

    expect(screen.getByText("Realized P/L").nextElementSibling).toHaveClass("text-[#ff3b45]");
    expect(screen.queryByText(formatCurrency(-120, "USD"))).not.toBeInTheDocument();
  });
});
