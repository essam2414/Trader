// Renders a table of realized trading performance broken down by ticker,
// paginated 10 rows/page. Displays an empty state message when there are no
// closed trades.

"use client";

import { formatCurrency } from "../lib/format";
import type { TickerPerformance } from "../lib/types";
import { Pagination } from "./Pagination";
import { usePagination } from "../lib/usePagination";

const PAGE_SIZE = 10;

export function TickerPerformanceTable({
  performanceByTicker,
  currency,
}: {
  performanceByTicker: TickerPerformance[];
  currency: string;
}) {
  const pagination = usePagination(performanceByTicker, PAGE_SIZE);

  if (performanceByTicker.length === 0) {
    return <p className="text-sm text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-neutral-800">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-800 bg-neutral-950/40">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">Ticker</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Realized P/L
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">Trades</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Win rate
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/60">
          {pagination.pageItems.map((row) => (
            <tr key={row.ticker} className="transition-colors hover:bg-neutral-800/40">
              <td className="px-4 py-3 font-medium text-neutral-100">{row.ticker}</td>
              <td className={`px-4 py-3 font-mono ${row.realizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {formatCurrency(row.realizedPnl, currency)}
              </td>
              <td className="px-4 py-3 font-mono text-neutral-300">{row.tradeCount}</td>
              <td className="px-4 py-3 font-mono text-neutral-300">{(row.winRate * 100).toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        rangeStart={pagination.rangeStart}
        rangeEnd={pagination.rangeEnd}
        totalCount={pagination.totalCount}
        canGoPrev={pagination.canGoPrev}
        canGoNext={pagination.canGoNext}
        onPrev={pagination.goToPrev}
        onNext={pagination.goToNext}
      />
    </div>
  );
}
