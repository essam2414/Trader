import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardAccountSummary, DashboardAccountSummarySkeleton } from "../DashboardAccountSummary";

vi.mock("../../lib/api", () => ({
  getPortfolioCurrent: vi.fn().mockResolvedValue({
    account: {
      totalValue: 1381.17,
      unrealizedProfitLoss: 0,
      currency: "GBP",
    },
  }),
}));

describe("DashboardAccountSummary", () => {
  it("reserves the same fixed summary band while loading and after data resolves", async () => {
    const { unmount } = render(<DashboardAccountSummarySkeleton />);
    expect(screen.getByLabelText(/loading account overview/i)).toHaveClass("h-[72px]");
    unmount();

    render(await DashboardAccountSummary());
    expect(screen.getByLabelText(/account overview/i)).toHaveClass("h-[72px]");
  });
});
