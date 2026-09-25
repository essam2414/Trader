import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  buildCumulativeRealizedPnlData,
  CumulativeRealizedPnlChart,
} from "../CumulativeRealizedPnlChart";

describe("CumulativeRealizedPnlChart", () => {
  it("orders closed-trade P/L chronologically and accumulates each broker-recorded amount", () => {
    const data = buildCumulativeRealizedPnlData([
      { takenAt: "2026-09-03T12:00:00Z", realizedPnl: 50 },
      { takenAt: "2026-09-01T12:00:00Z", realizedPnl: -10 },
      { takenAt: "2026-09-02T12:00:00Z", realizedPnl: 20 },
    ]);

    expect(data).toEqual([
      { timestamp: Date.parse("2026-09-01T12:00:00Z"), value: -10 },
      { timestamp: Date.parse("2026-09-02T12:00:00Z"), value: 10 },
      { timestamp: Date.parse("2026-09-03T12:00:00Z"), value: 60 },
    ]);
  });

  it("shows an empty state until the account has a closed trade", () => {
    render(<CumulativeRealizedPnlChart points={[]} currency="GBP" />);

    expect(screen.getByText(/no realised p\/l yet/i)).toBeInTheDocument();
  });
});
