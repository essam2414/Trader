import { CumulativeRealizedPnlChart } from "./CumulativeRealizedPnlChart";
import { PerformanceMetrics } from "./PerformanceMetrics";
import { PortfolioSummary } from "./PortfolioSummary";
import { PositionsTable } from "./PositionsTable";
import { getPortfolioCurrent, getPortfolioMetrics } from "../lib/api";

export async function PortfolioOverview() {
  const [current, metrics] = await Promise.all([
    getPortfolioCurrent(),
    getPortfolioMetrics(),
  ]);
  const cashDrag = current.account.totalValue
    ? current.account.cash.availableToTrade / current.account.totalValue
    : 0;

  return (
    <>
      <section className="grid grid-cols-[1fr_minmax(0,4fr)] gap-x-10 border-b border-neutral-800 pb-6">
        <PortfolioSummary
          account={current.account}
          totalWinningTradePnl={metrics.totalWinningTradePnl}
          totalLosingTradePnl={metrics.totalLosingTradePnl}
        />

        <section aria-labelledby="cumulative-realized-pnl-heading">
          <h2
            id="cumulative-realized-pnl-heading"
            className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500"
          >
            Cumulative realised P/L
          </h2>
          <CumulativeRealizedPnlChart points={metrics.realizedPnlTimeline} currency={current.account.currency} />
        </section>
      </section>

      <section className="py-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Open positions</h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>

      <section className="border-t border-neutral-800 py-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Performance</h2>
        <PerformanceMetrics metrics={metrics} cashDrag={cashDrag} currency={current.account.currency} />
      </section>
    </>
  );
}

export function PortfolioOverviewSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading portfolio overview">
      <section className="grid grid-cols-[1fr_minmax(0,4fr)] gap-x-10 border-b border-neutral-800 pb-6">
        <section className="flex flex-col gap-y-6" aria-label="Trade outcome summary">
          {["Realized P/L", "Good trades", "Bad trades"].map((label) => (
            <article key={label}>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{label}</p>
              <div className="mt-2 h-10 w-40 animate-pulse rounded bg-neutral-800" />
            </article>
          ))}
        </section>
        <section>
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">Cumulative realised P/L</h2>
          <div className="h-[280px] animate-pulse rounded bg-neutral-800" />
        </section>
      </section>
      {["Open positions", "Performance"].map((label) => (
        <section key={label} className={label === "Open positions" ? "py-6" : "border-t border-neutral-800 py-6"}>
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">{label}</h2>
          <div className="h-32 animate-pulse rounded bg-neutral-800" />
        </section>
      ))}
      <span className="sr-only" role="status">Loading portfolio overview</span>
    </div>
  );
}
