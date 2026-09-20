// Main dashboard Server Component: fetches live portfolio data from the backend API
// server-side (so BACKEND_URL/DASHBOARD_API_KEY never reach the browser) and renders
// the summary, equity curve, positions table, and performance metrics.
export const dynamic = "force-dynamic";

import { EquityCurveChart } from "../components/EquityCurveChart";
import { PerformanceMetrics } from "../components/PerformanceMetrics";
import { PortfolioSummary } from "../components/PortfolioSummary";
import { PortfolioAutoRefresh } from "../components/PortfolioAutoRefresh";
import { PositionsTable } from "../components/PositionsTable";
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
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <PortfolioAutoRefresh />
      <header className="flex items-baseline gap-3">
        <span className="h-2 w-2 rounded-full bg-neutral-100" aria-hidden="true" />
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-100">Portfolio overview</h1>
      </header>

      <PortfolioSummary account={current.account} />

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Value over time
        </h2>
        <EquityCurveChart snapshots={history} />
      </section>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Open positions
        </h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Performance</h2>
        <PerformanceMetrics metrics={metrics} cashDrag={cashDrag} currency={current.account.currency} />
      </section>
    </main>
  );
}
