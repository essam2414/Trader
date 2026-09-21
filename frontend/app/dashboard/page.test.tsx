import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../components/PortfolioAutoRefresh", () => ({
  PortfolioAutoRefresh: () => <div data-testid="portfolio-auto-refresh" />,
}));

vi.mock("../../components/DashboardAccountSummary", () => ({
  DashboardAccountSummary: () => <div>Account summary</div>,
  DashboardAccountSummarySkeleton: () => <div>Loading account summary</div>,
}));

vi.mock("../../components/NewsSection", () => ({
  NewsSection: () => <div>News</div>,
}));

vi.mock("../../components/WatchlistSection", () => ({
  WatchlistSection: () => <div>Watchlist</div>,
}));

import DashboardPage from "./page";

describe("DashboardPage", () => {
  it("does not perform route-wide portfolio refreshes that remount the watchlist", () => {
    render(<DashboardPage />);

    expect(screen.queryByTestId("portfolio-auto-refresh")).not.toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveClass("h-screen", "overflow-hidden");
  });
});
