// Generic client-side pagination for tables that already have their full
// item list in memory (as opposed to server-side paged fetching). Used by
// TickerPerformanceTable and TradeHistoryTable.

"use client";

import { useMemo, useState } from "react";

export interface Pagination<T> {
  pageItems: T[];
  page: number;
  pageCount: number;
  rangeStart: number;
  rangeEnd: number;
  totalCount: number;
  canGoPrev: boolean;
  canGoNext: boolean;
  goToFirst: () => void;
  goToPrev: () => void;
  goToNext: () => void;
}

export function usePagination<T>(items: T[], pageSize: number): Pagination<T> {
  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pageCount);

  const pageItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, currentPage, pageSize]);

  const rangeStart = items.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const rangeEnd = Math.min(currentPage * pageSize, items.length);

  return {
    pageItems,
    page: currentPage,
    pageCount,
    rangeStart,
    rangeEnd,
    totalCount: items.length,
    canGoPrev: currentPage > 1,
    canGoNext: currentPage < pageCount,
    goToFirst: () => setPage(1),
    goToPrev: () => setPage((p) => Math.max(1, p - 1)),
    goToNext: () => setPage((p) => Math.min(pageCount, p + 1)),
  };
}
