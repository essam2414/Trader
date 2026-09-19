// Main dashboard Server Component: fetches live portfolio data from the backend API
// server-side (so BACKEND_URL/DASHBOARD_API_KEY never reach the browser) and renders
// the summary, equity curve, positions table, and performance metrics.
export const dynamic = "force-dynamic";

import { EquityCurveChart } from "../components/EquityCurveChart";
import { PerformanceMetrics } from "../components/PerformanceMetrics";
import { PortfolioSummary } from "../components/PortfolioSummary";
import { PositionsTable } from "../components/PositionsTable";
import { TickerPerformanceTable } from "../components/TickerPerformanceTable";
import { getPortfolioCurrent, getPortfolioHistory, getPortfolioMetrics } from "../lib/api";

export default async function DashboardPage() {
  const [current, history, metrics] = await Promise.all([
    getPortfolioCurrent(),
    getPortfolioHistory(),
    getPortfolioMetrics(),
  ]);
  const cashDrag = current.account.totalValue
    ? current.account.cash.availableToTrade / current.account.totalValue
    : 0;

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <h1 className="text-3xl font-bold">Portfolio dashboard</h1>
      <PortfolioSummary account={current.account} />
      <section>
        <h2 className="mb-4 text-xl font-semibold">Value over time</h2>
        <EquityCurveChart snapshots={history} />
      </section>
      <section>
        <h2 className="mb-4 text-xl font-semibold">Open positions</h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>
      <section>
        <h2 className="mb-4 text-xl font-semibold">Performance</h2>
        <PerformanceMetrics metrics={metrics} cashDrag={cashDrag} currency={current.account.currency} />
        <div className="mt-6">
          <TickerPerformanceTable
            performanceByTicker={metrics.performanceByTicker}
            currency={current.account.currency}
          />
        </div>
      </section>
    </main>
  );
}
