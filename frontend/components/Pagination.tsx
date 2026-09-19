// Prev/Next pagination controls with a "range of total" label. Purely
// presentational — pairs with the usePagination hook, which owns the state.

export function Pagination({
  rangeStart,
  rangeEnd,
  totalCount,
  canGoPrev,
  canGoNext,
  onPrev,
  onNext,
}: {
  rangeStart: number;
  rangeEnd: number;
  totalCount: number;
  canGoPrev: boolean;
  canGoNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
      <p className="font-mono text-xs text-zinc-500">
        {rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} of {totalCount.toLocaleString()}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onPrev}
          disabled={!canGoPrev}
          className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-amber-500/50 hover:text-amber-400 disabled:pointer-events-none disabled:opacity-30"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!canGoNext}
          className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-amber-500/50 hover:text-amber-400 disabled:pointer-events-none disabled:opacity-30"
        >
          Next
        </button>
      </div>
    </div>
  );
}
