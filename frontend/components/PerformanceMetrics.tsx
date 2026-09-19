// Renders a stats grid of trade performance and account-level metrics: realized
// P/L, win rate, expectancy, profit factor, payoff ratio, holding period, max
// drawdown, cash drag, and dividend income. Trade-derived figures default to
// 0 (or a dash for ratios undefined with no losing trades) when there are no
// closed trades yet, so the grid always renders rather than needing an
// empty-state gate.

import { formatCurrency } from "../lib/format";
import type { PortfolioMetrics } from "../lib/types";

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatRatio(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

export function PerformanceMetrics({ metrics, currency }: { metrics: PortfolioMetrics; currency: string }) {
  const isProfit = metrics.realizedPnl >= 0;
  return (
    <div className="grid grid-cols-2 gap-4 rounded-lg border border-neutral-200 p-6 sm:grid-cols-4">
      <div>
        <p className="text-sm text-neutral-500">Realized P/L</p>
        <p className={`text-2xl font-semibold ${isProfit ? "text-green-600" : "text-red-600"}`}>
          {formatCurrency(metrics.realizedPnl, currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Win rate</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.winRate)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Expectancy</p>
        <p className="text-2xl font-semibold">{formatCurrency(metrics.expectancy, currency)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Profit factor</p>
        <p className="text-2xl font-semibold">{formatRatio(metrics.profitFactor)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Payoff ratio</p>
        <p className="text-2xl font-semibold">{formatRatio(metrics.payoffRatio)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Avg. holding period</p>
        <p className="text-2xl font-semibold">{(metrics.averageHoldingPeriodHours / 24).toFixed(1)}d</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Max drawdown</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.maxDrawdown)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Cash drag</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.cashDrag)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Dividend income</p>
        <p className="text-2xl font-semibold">{formatCurrency(metrics.dividendIncome, currency)}</p>
      </div>
    </div>
  );
}
