// Renders a table of realized trading performance broken down by ticker,
// paginated 10 rows/page. Displays an empty state message when there are no
// closed trades.

"use client";

import { useMemo, useState } from "react";
import { formatCurrency, formatTicker } from "../lib/format";
import type { TickerPerformance } from "../lib/types";
import { Pagination } from "./Pagination";
import { usePagination } from "../lib/usePagination";

const PAGE_SIZE = 10;
type SortColumn = "ticker" | "realizedPnl" | "tradeCount" | "winRate";
type SortDirection = "ascending" | "descending";

const defaultSortDirection: Record<SortColumn, SortDirection> = {
  ticker: "ascending",
  realizedPnl: "descending",
  tradeCount: "descending",
  winRate: "descending",
};

function SortableHeader({
  column,
  label,
  sortColumn,
  sortDirection,
  onSort,
}: {
  column: SortColumn;
  label: string;
  sortColumn: SortColumn | null;
  sortDirection: SortDirection;
  onSort: (column: SortColumn) => void;
}) {
  const isActive = sortColumn === column;
  const ariaSort = isActive ? sortDirection : "none";
  const indicator = !isActive ? "↕" : sortDirection === "ascending" ? "↑" : "↓";

  return (
    <th
      aria-sort={ariaSort}
      className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500"
    >
      <button
        type="button"
        aria-label={`Sort by ${label}`}
        className="inline-flex items-center gap-1 transition-colors hover:text-neutral-100 focus:outline-none focus-visible:text-neutral-100"
        onClick={() => onSort(column)}
      >
        {label}
        <span aria-hidden="true" className={isActive ? "text-neutral-100" : "text-neutral-600"}>
          {indicator}
        </span>
      </button>
    </th>
  );
}

export function TickerPerformanceTable({
  performanceByTicker,
  currency,
}: {
  performanceByTicker: TickerPerformance[];
  currency: string;
}) {
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("ascending");
  const sortedPerformance = useMemo(() => {
    if (sortColumn === null) return performanceByTicker;

    const direction = sortDirection === "ascending" ? 1 : -1;
    return [...performanceByTicker].sort((left, right) => {
      if (sortColumn === "ticker") {
        return formatTicker(left.ticker).localeCompare(formatTicker(right.ticker)) * direction;
      }
      return (left[sortColumn] - right[sortColumn]) * direction;
    });
  }, [performanceByTicker, sortColumn, sortDirection]);
  const pagination = usePagination(sortedPerformance, PAGE_SIZE);

  function sortBy(column: SortColumn) {
    setSortColumn(column);
    if (sortColumn !== column) {
      setSortDirection(defaultSortDirection[column]);
    } else {
      setSortDirection((direction) => (direction === "ascending" ? "descending" : "ascending"));
    }
    pagination.goToFirst();
  }

  if (performanceByTicker.length === 0) {
    return <p className="text-sm text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-neutral-800">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-neutral-800">
            <SortableHeader
              column="ticker"
              label="Ticker"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={sortBy}
            />
            <SortableHeader
              column="realizedPnl"
              label="Realized P/L"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={sortBy}
            />
            <SortableHeader
              column="tradeCount"
              label="Trades"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={sortBy}
            />
            <SortableHeader
              column="winRate"
              label="Win rate"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={sortBy}
            />
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/60">
          {pagination.pageItems.map((row) => (
            <tr key={row.ticker} className="transition-colors hover:bg-neutral-800/40">
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] sm:text-[16px]">
                {formatTicker(row.ticker)}
              </td>
              <td
                className={`px-4 py-3 text-[15px] font-semibold [font-variant-numeric:tabular-nums] sm:text-[16px] ${row.realizedPnl > 0 ? "text-[#32e64d]" : row.realizedPnl < 0 ? "text-[#ff3b45]" : "text-neutral-100"}`}
              >
                {formatCurrency(Math.abs(row.realizedPnl), currency)}
              </td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">
                {row.tradeCount}
              </td>
              <td className="px-4 py-3 text-[15px] font-semibold text-[#f5f5f5] [font-variant-numeric:tabular-nums] sm:text-[16px]">
                {(row.winRate * 100).toFixed(0)}%
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
