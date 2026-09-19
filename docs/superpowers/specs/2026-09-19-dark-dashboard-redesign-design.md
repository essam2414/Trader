# Dark Dashboard Redesign — Design

## Status

Approved. Ready for implementation.

## Purpose

The dashboard currently renders with default light Tailwind styling (bare text, minimal
borders, no card treatment) and both data tables (`TickerPerformanceTable`,
`TradeHistoryTable`) render their entire row set unpaginated — the trade history table alone
now has ~1,791 rows. This redesign gives the whole dashboard a modern, dark-themed, card-based
visual treatment and adds client-side pagination (10 rows/page, Prev/Next) to both tables.

## Scope

**In scope:** visual redesign of every existing dashboard section (summary tiles, equity
chart, positions table, performance stats, ticker performance table, trade history table);
pagination for the two tables.

**Explicitly out of scope:** a light/dark toggle (dark-only, per decision); server-side
pagination (client-side slicing of the already-fetched list, per decision); any new data or
API changes — this is a pure frontend/visual + pagination change, no backend files touched;
sorting/filtering the tables (not requested).

## Visual direction

- **Palette:** page background `zinc-950`; card surfaces `zinc-900` with `zinc-800` borders;
  primary text `zinc-100`; muted/secondary text `zinc-400`. Accent color **amber**
  (`amber-500`/`amber-400`) for interactive elements (buttons, pagination controls, focus
  rings) — chosen over the common blue/purple AI-dashboard default for a more distinctive,
  professional feel. P&L keeps its semantic green/red meaning but in dark-mode-appropriate
  shades: `emerald-400` (profit) / `rose-400` (loss).
- **Typography:** **Manrope** for UI text, **JetBrains Mono** for all numeric/financial values
  (prices, quantities, P&L, percentages) so columns align on tabular digits. Both loaded via
  `next/font/google` (self-hosted by Next.js at build time, no extra runtime requests, no CSP
  concerns).
- **Layout:** every section becomes a bordered, padded card (`rounded-lg border border-zinc-800
  bg-zinc-900 p-6`) instead of a bare text block; section headers get a small uppercase
  tracking-wide muted-color label.
- **Tables:** card-wrapped, tinted header row (`bg-zinc-950/40`) with uppercase tracking-wide
  column labels, per-row hover highlight (`hover:bg-zinc-800/50`), right-aligned tabular
  numeric columns (monospace, via the JetBrains Mono font applied globally to numeric cells),
  color-coded P&L, `px-4 py-3` row padding (up from the current bare `py-2`).

## Pagination

- **`frontend/lib/usePagination.ts`** — a generic hook: `usePagination<T>(items: T[], pageSize:
  number)` returning `{ pageItems, page, pageCount, goToNext, goToPrev, canGoNext, canGoPrev,
  rangeStart, rangeEnd, totalCount }`. Pure logic, no rendering — unit-testable in isolation
  with plain arrays (no React Testing Library needed for the hook itself, only for components
  that use it).
- **`frontend/components/Pagination.tsx`** — presentational: Prev/Next buttons (disabled at
  the bounds) plus a "`{rangeStart}–{rangeEnd} of {totalCount}`" range label. Takes the values
  the hook produces as props, so it has no pagination logic of its own.
- **`TickerPerformanceTable`** and **`TradeHistoryTable`** both become `"use client"` components
  (matching the existing pattern `EquityCurveChart` already uses for its own client-side
  needs), each calling `usePagination` on the full list they already receive as a prop and
  rendering `Pagination` below their table body. Page size is 10 for both, fixed (not
  user-configurable) — matches the request, no need to over-build a page-size selector.
- Pagination state resets implicitly on every full page load (Next Server Component refetch),
  which is the expected/desired behavior — there's no need to persist "which page was I on"
  across a dashboard reload.

## File scope

**New:**
- `frontend/lib/usePagination.ts`
- `frontend/lib/__tests__/usePagination.test.ts`
- `frontend/components/Pagination.tsx`
- `frontend/components/__tests__/Pagination.test.tsx`

**Modified (visual restyle + pagination wiring):**
- `frontend/app/layout.tsx` — load Manrope/JetBrains Mono, apply dark background to `<body>`
- `frontend/app/globals.css` — CSS custom properties for the palette if needed beyond Tailwind
  utility classes (kept minimal; Tailwind utilities do most of the work)
- `frontend/app/page.tsx` — card-wrapped sections, dark section headers
- `frontend/components/PortfolioSummary.tsx`
- `frontend/components/PositionsTable.tsx`
- `frontend/components/EquityCurveChart.tsx` — dark-mode chart colors (axis/line/tooltip)
- `frontend/components/PerformanceMetrics.tsx`
- `frontend/components/TickerPerformanceTable.tsx` — dark restyle + pagination
- `frontend/components/TradeHistoryTable.tsx` — dark restyle + pagination
- Their existing test files — updated only where pagination changes what's queryable (e.g.
  a test asserting all 1,791 rows render no longer holds; tests instead assert the first page
  renders and Prev/Next work), not for pure visual/className changes, which existing tests
  don't and shouldn't assert on.

**Not touched:** any backend file, `lib/api.ts`, `lib/types.ts` — this is a pure frontend
visual + client-side pagination change.

## Testing

- `usePagination` — unit tests (plain array fixtures): first page slice, `canGoNext`/
  `canGoPrev` at both bounds, `goToNext`/`goToPrev` behavior, `pageCount` calculation
  (including a non-exact-multiple case), `rangeStart`/`rangeEnd` labels.
- `Pagination` — render test: buttons disabled at bounds, range label renders correctly,
  clicking Next/Prev calls the provided handlers.
- `TickerPerformanceTable` / `TradeHistoryTable` — updated to assert pagination behavior with
  fixtures of >10 items (first page shows first 10, clicking Next reveals the next page,
  Prev is disabled on page 1), replacing/extending their existing single-page tests.
- No backend tests affected (no backend changes).
- Manual verification: `npm run dev`, visually confirm the dark theme renders correctly and
  pagination works for both tables against real data (the account has ~1,791 trades to
  page through).
