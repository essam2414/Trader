import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getPortfolioCurrent } from "../../lib/api";
import { DashboardAccountSummary, DashboardAccountSummarySkeleton } from "../DashboardAccountSummary";
import { LiveDashboardAccountSummary } from "../LiveDashboardAccountSummary";

vi.mock("../../lib/api", () => ({
  getPortfolioCurrent: vi.fn().mockResolvedValue({
    account: {
      totalValue: 1381.17,
      cash: { availableToTrade: 250, inPies: 0, reservedForOrders: 0 },
      unrealizedProfitLoss: 0,
      weeklyRealizedProfitLoss: 25,
      currency: "GBP",
    },
  }),
}));

describe("DashboardAccountSummary", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("reserves the same fixed summary band while loading and after data resolves", async () => {
    const { unmount } = render(<DashboardAccountSummarySkeleton />);
    expect(screen.getByLabelText(/loading account overview/i)).toHaveClass("h-[72px]");
    expect(screen.getByLabelText(/loading account overview/i)).toHaveClass("justify-around");
    unmount();

    render(await DashboardAccountSummary());
    expect(screen.getByLabelText(/account overview/i)).toHaveClass("h-[72px]");
    expect(screen.getByLabelText(/account overview/i)).toHaveClass("justify-around");
  });

  it("shows cash available immediately after total account value", () => {
    render(
      <LiveDashboardAccountSummary
        initialAccount={{
          ...accountWithUnrealizedPnl(10),
          cash: { availableToTrade: 250, inPies: 0, reservedForOrders: 0 },
        }}
      />
    );

    expect(screen.getByText("Total account value").compareDocumentPosition(screen.getByText("Cash available")))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.getByText("£250.00")).toBeInTheDocument();
  });

  it("uses the watchlist's bright gain and loss colours for unrealised P/L", async () => {
    vi.mocked(getPortfolioCurrent)
      .mockResolvedValueOnce({ account: accountWithUnrealizedPnl(12), positions: [] })
      .mockResolvedValueOnce({ account: accountWithUnrealizedPnl(-12), positions: [] });

    const { unmount } = render(await DashboardAccountSummary());
    expect(screen.getByText(/12/)).toHaveClass("text-[#32e64d]");
    unmount();

    render(await DashboardAccountSummary());
    expect(screen.getByText(/12/)).toHaveClass("text-[#ff3b45]");
  });

  it("shows this week's realised P/L beside unrealised P/L", async () => {
    render(await DashboardAccountSummary());

    expect(screen.getByText("Weekly gain")).toBeInTheDocument();
    expect(screen.getByText(/25\.00/)).toHaveClass("text-[#32e64d]");
  });

  it("shows an unsigned weekly loss while retaining its loss colour", () => {
    render(<LiveDashboardAccountSummary initialAccount={accountWithUnrealizedPnl(0, 1000, -25)} />);

    expect(screen.getByText("£25.00")).toHaveClass("text-[#ff3b45]");
    expect(screen.queryByText("-£25.00")).not.toBeInTheDocument();
  });

  it("updates account value and unrealised P/L from the portfolio endpoint every five seconds", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ account: accountWithUnrealizedPnl(12, 1012) }),
    });

    render(<LiveDashboardAccountSummary initialAccount={accountWithUnrealizedPnl(-5, 995, -3)} />);
    expect(screen.getByText("£995.00")).toBeInTheDocument();
    expect(screen.getByText("£5.00")).toHaveClass("text-[#ff3b45]");
    expect(screen.queryByText("-£5.00")).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/portfolio/current", { cache: "no-store" });
    expect(screen.getByText("£1,012.00")).toBeInTheDocument();
    expect(screen.getByText("£12.00")).toHaveClass("text-[#32e64d]");
  });
});

function accountWithUnrealizedPnl(unrealizedProfitLoss: number, totalValue = 1000, weeklyRealizedProfitLoss = 25) {
  return {
    id: 1,
    totalValue,
    unrealizedProfitLoss,
    weeklyRealizedProfitLoss,
    currency: "GBP",
    cash: { availableToTrade: 0, inPies: 0, reservedForOrders: 0 },
    realizedProfitLoss: 0,
  };
}
