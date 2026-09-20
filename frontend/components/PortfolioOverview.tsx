import { EquityCurveChart } from "./EquityCurveChart";
import { PerformanceMetrics } from "./PerformanceMetrics";
import { PortfolioSummary } from "./PortfolioSummary";
import { PositionsTable } from "./PositionsTable";
import { getPortfolioCurrent, getPortfolioHistory, getPortfolioMetrics } from "../lib/api";

export async function PortfolioOverview() {
  const [current, history, metrics] = await Promise.all([
    getPortfolioCurrent(),
    getPortfolioHistory(),
    getPortfolioMetrics(),
  ]);
  const cashDrag = current.account.totalValue
    ? current.account.cash.availableToTrade / current.account.totalValue
    : 0;

  return (
    <>
      <PortfolioSummary account={current.account} />

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Value over time</h2>
        <EquityCurveChart snapshots={history} />
      </section>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Open positions</h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Performance</h2>
        <PerformanceMetrics metrics={metrics} cashDrag={cashDrag} currency={current.account.currency} />
      </section>
    </>
  );
}

export function PortfolioOverviewSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading portfolio overview">
      <section className="grid grid-cols-3 gap-5">
        {["Account value", "Cash available", "Unrealised P/L"].map((label) => (
          <article key={label} className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-neutral-500">{label}</p>
            <div className="mt-3 h-9 w-40 animate-pulse rounded bg-neutral-800" />
          </article>
        ))}
      </section>
      {["Value over time", "Open positions", "Performance"].map((label) => (
        <section key={label} className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">{label}</h2>
          <div className="h-32 animate-pulse rounded bg-neutral-800" />
        </section>
      ))}
      <span className="sr-only" role="status">Loading portfolio overview</span>
    </div>
  );
}
