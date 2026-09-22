// Renders a stats grid of trade performance and account-level metrics: realized
// P/L, win rate, expectancy, profit factor, payoff ratio, holding period, max
// drawdown, cash drag, and dividend income. Trade-derived figures default to
// 0 (or a dash for ratios undefined with no losing trades) when there are no
// closed trades yet, so the grid always renders rather than needing an
// empty-state gate.
//
// cashDrag is a separate prop, not part of `metrics`: it's derived from the
// account summary the page already fetches for the portfolio summary
// section, rather than /api/portfolio/metrics making its own redundant
// Trading212 call just to compute the same ratio.

import { formatCurrency } from "../lib/format";
import type { PortfolioMetrics } from "../lib/types";

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatRatio(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

function ratioColor(value: number | null): string {
  if (value === null) return "text-neutral-100";
  return value >= 1 ? "text-[#32e64d]" : "text-[#ff3b45]";
}

function Tile({ label, value, valueClassName = "text-neutral-100" }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${valueClassName}`}>{value}</p>
    </div>
  );
}

export function PerformanceMetrics({
  metrics,
  cashDrag,
  currency,
}: {
  metrics: PortfolioMetrics;
  cashDrag: number;
  currency: string;
}) {
  const isProfit = metrics.realizedPnl >= 0;
  return (
    <div className="grid grid-cols-2 divide-x divide-y divide-neutral-800 overflow-hidden rounded-lg border border-neutral-800 sm:grid-cols-3 sm:divide-y-0">
      <Tile
        label="Realized P/L"
        value={formatCurrency(metrics.realizedPnl, currency)}
        valueClassName={isProfit ? "text-[#32e64d]" : "text-[#ff3b45]"}
      />
      <Tile label="Win rate" value={formatPercent(metrics.winRate)} />
      <Tile label="Expectancy" value={formatCurrency(metrics.expectancy, currency)} />
      <Tile
        label="Profit factor"
        value={formatRatio(metrics.profitFactor)}
        valueClassName={ratioColor(metrics.profitFactor)}
      />
      <Tile
        label="Payoff ratio"
        value={formatRatio(metrics.payoffRatio)}
        valueClassName={ratioColor(metrics.payoffRatio)}
      />
      <Tile label="Avg. holding period" value={`${(metrics.averageHoldingPeriodHours / 24).toFixed(1)}d`} />
      <Tile label="Max drawdown" value={formatPercent(metrics.maxDrawdown)} />
      <Tile label="Cash drag" value={formatPercent(cashDrag)} />
      <Tile label="Dividend income" value={formatCurrency(metrics.dividendIncome, currency)} />
    </div>
  );
}
