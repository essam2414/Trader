// Tests for usePagination: verifies page slicing, bounds, and navigation
// for the client-side table pagination used by TickerPerformanceTable and
// TradeHistoryTable.

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePagination } from "../usePagination";

const ITEMS = Array.from({ length: 25 }, (_, i) => i + 1); // [1, 2, ..., 25]

describe("usePagination", () => {
  it("returns the first page of items and correct bounds/labels on initial render", () => {
    const { result } = renderHook(() => usePagination(ITEMS, 10));

    expect(result.current.pageItems).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(result.current.page).toBe(1);
    expect(result.current.pageCount).toBe(3);
    expect(result.current.rangeStart).toBe(1);
    expect(result.current.rangeEnd).toBe(10);
    expect(result.current.totalCount).toBe(25);
    expect(result.current.canGoPrev).toBe(false);
    expect(result.current.canGoNext).toBe(true);
  });

  it("advances to the next page and slices correctly, including a partial final page", () => {
    const { result } = renderHook(() => usePagination(ITEMS, 10));

    act(() => result.current.goToNext());
    expect(result.current.pageItems).toEqual([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
    expect(result.current.rangeStart).toBe(11);
    expect(result.current.rangeEnd).toBe(20);

    act(() => result.current.goToNext());
    expect(result.current.pageItems).toEqual([21, 22, 23, 24, 25]); // partial last page
    expect(result.current.rangeEnd).toBe(25);
    expect(result.current.canGoNext).toBe(false);
    expect(result.current.canGoPrev).toBe(true);
  });

  it("does not advance past the last page or before the first page", () => {
    const { result } = renderHook(() => usePagination(ITEMS, 10));

    act(() => result.current.goToPrev()); // already on page 1
    expect(result.current.page).toBe(1);

    act(() => result.current.goToNext());
    act(() => result.current.goToNext());
    act(() => result.current.goToNext()); // already on last page (3)
    expect(result.current.page).toBe(3);
  });

  it("returns to the first page", () => {
    const { result } = renderHook(() => usePagination(ITEMS, 10));

    act(() => result.current.goToNext());
    act(() => result.current.goToFirst());

    expect(result.current.page).toBe(1);
    expect(result.current.pageItems).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  it("handles fewer items than one page", () => {
    const { result } = renderHook(() => usePagination([1, 2, 3], 10));

    expect(result.current.pageItems).toEqual([1, 2, 3]);
    expect(result.current.pageCount).toBe(1);
    expect(result.current.canGoNext).toBe(false);
    expect(result.current.canGoPrev).toBe(false);
    expect(result.current.rangeEnd).toBe(3);
  });

  it("handles an empty list without error", () => {
    const { result } = renderHook(() => usePagination([], 10));

    expect(result.current.pageItems).toEqual([]);
    expect(result.current.pageCount).toBe(1);
    expect(result.current.rangeStart).toBe(0);
    expect(result.current.rangeEnd).toBe(0);
    expect(result.current.totalCount).toBe(0);
  });
});
