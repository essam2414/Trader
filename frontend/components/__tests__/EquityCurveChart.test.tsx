// Tests for EquityCurveChart: verifies the empty state and that a chart renders given snapshot data.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EquityCurveChart } from "../EquityCurveChart";

describe("EquityCurveChart", () => {
  it("shows an empty state when there is no history yet", () => {
    render(<EquityCurveChart snapshots={[]} />);

    expect(screen.getByText(/not enough history yet/i)).toBeInTheDocument();
  });

  it("renders a chart container when given snapshot data", () => {
    render(
      <EquityCurveChart
        snapshots={[
          { takenAt: "2026-09-01T00:00:00Z", totalValue: 10000, unrealizedProfitLoss: 100 },
          { takenAt: "2026-09-02T00:00:00Z", totalValue: 10200, unrealizedProfitLoss: 300 },
        ]}
      />
    );

    expect(document.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });
});
