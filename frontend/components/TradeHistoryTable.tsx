// Renders a table of individual closed trades (entry/exit price, quantity,
// dates, P/L, holding period), newest first, paginated 10 rows/page.
// Displays an empty state message when there are no closed trades.

"use client";

import { formatCurrency } from "../lib/format";
import type { Trade } from "../lib/types";
import { Pagination } from "./Pagination";
import { usePagination } from "../lib/usePagination";

const PAGE_SIZE = 10;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

function formatHoldingPeriod(hours: number): string {
  return `${(hours / 24).toFixed(1)}d`;
}

export function TradeHistoryTable({ trades, currency }: { trades: Trade[]; currency: string }) {
  const pagination = usePagination(trades, PAGE_SIZE);

  if (trades.length === 0) {
    return <p className="text-sm text-zinc-500">No closed trades yet.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-zinc-800">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-950/40">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Ticker</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Entry date
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Entry price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Exit date
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Exit price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Quantity
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Held</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">P/L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60">
          {pagination.pageItems.map((trade, index) => (
            <tr
              key={`${trade.ticker}-${trade.entryAt}-${trade.exitAt}-${index}`}
              className="transition-colors hover:bg-zinc-800/40"
            >
              <td className="px-4 py-3 font-medium text-zinc-100">{trade.ticker}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">{formatDate(trade.entryAt)}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">
                {formatCurrency(trade.entryPrice, currency)}
              </td>
              <td className="px-4 py-3 font-mono text-zinc-300">{formatDate(trade.exitAt)}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">
                {formatCurrency(trade.exitPrice, currency)}
              </td>
              <td className="px-4 py-3 font-mono text-zinc-300">{trade.quantity}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">{formatHoldingPeriod(trade.holdingPeriodHours)}</td>
              <td className={`px-4 py-3 font-mono ${trade.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {formatCurrency(trade.pnl, currency)}
              </td>
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
