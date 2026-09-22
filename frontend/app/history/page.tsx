import { TickerPerformanceTable } from "../../components/TickerPerformanceTable";
import { TradeHistoryTable } from "../../components/TradeHistoryTable";
import { PageAutoRefresh } from "../../components/PortfolioAutoRefresh";
import { getPortfolioCurrent, getPortfolioMetrics } from "../../lib/api";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const [current, metrics] = await Promise.all([getPortfolioCurrent(), getPortfolioMetrics()]);

  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <PageAutoRefresh intervalMs={60_000} />

      <section>
        <h2 className="mb-4 text-xl font-semibold tracking-tight text-neutral-100">
          Trade history
        </h2>
        <TradeHistoryTable trades={metrics.trades} currency={current.account.currency} />
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold tracking-tight text-neutral-100">
          Performance by ticker
        </h2>
        <TickerPerformanceTable
          performanceByTicker={metrics.performanceByTicker}
          currency={current.account.currency}
        />
      </section>
    </main>
  );
}
