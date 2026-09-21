// Renders a table of individual closed trades (entry/exit price, quantity,
// dates, P/L, holding period), newest first, paginated 10 rows/page.
// Displays an empty state message when there are no closed trades.

"use client";

import { formatCurrency, formatTicker } from "../lib/format";
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
    return <p className="text-sm text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-neutral-800">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-neutral-800">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Ticker</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Entry date
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Entry price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Exit date
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Exit price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Quantity
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Held</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">P/L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/60">
          {pagination.pageItems.map((trade, index) => (
            <tr
              key={`${trade.ticker}-${trade.entryAt}-${trade.exitAt}-${index}`}
              className="transition-colors hover:bg-neutral-800/40"
            >
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] sm:text-[16px]">{formatTicker(trade.ticker)}</td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">{formatDate(trade.entryAt)}</td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">
                {formatCurrency(trade.entryPrice, currency)}
              </td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">{formatDate(trade.exitAt)}</td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">
                {formatCurrency(trade.exitPrice, currency)}
              </td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">
                {trade.quantity.toFixed(2)}
              </td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">{formatHoldingPeriod(trade.holdingPeriodHours)}</td>
              <td className={`px-4 py-3 text-[15px] font-semibold [font-variant-numeric:tabular-nums] sm:text-[16px] ${trade.pnl > 0 ? "text-[#32e64d]" : trade.pnl < 0 ? "text-[#ff3b45]" : "text-neutral-100"}`}>
                {formatCurrency(Math.abs(trade.pnl), currency)}
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
