import { TickerPerformanceTable } from "../../components/TickerPerformanceTable";
import { TradeHistoryTable } from "../../components/TradeHistoryTable";
import { getPortfolioCurrent, getPortfolioMetrics } from "../../lib/api";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const [current, metrics] = await Promise.all([getPortfolioCurrent(), getPortfolioMetrics()]);

  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <header className="flex items-baseline gap-3">
        <span className="h-2 w-2 rounded-full bg-neutral-100" aria-hidden="true" />
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-100">History</h1>
      </header>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Performance by ticker
        </h2>
        <TickerPerformanceTable
          performanceByTicker={metrics.performanceByTicker}
          currency={current.account.currency}
        />
      </section>

      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Trade history
        </h2>
        <TradeHistoryTable trades={metrics.trades} currency={current.account.currency} />
      </section>
    </main>
  );
}
