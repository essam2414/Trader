# Trade Performance Metrics — Design

## Status

Approved. Ready for implementation planning.

## Purpose

Phase 1 gives a read-only, live snapshot of the portfolio (current positions, account
totals, equity curve). It has no view into *trading performance* — there's no way to see
whether trades are actually profitable, how good the win rate is, how long positions are
typically held, or which tickers are worth continuing to trade. This feature adds that view,
computed entirely from data already available via the Trading212 API, and surfaces it as a
new "Performance" section on the existing dashboard.

## Scope

**In scope:** every metric computable from Trading212's own historical order and dividend
data, plus drawdown (already derivable from the `portfolio_snapshots` table this app already
maintains).

**Explicitly out of scope for this iteration:**
- **MFE / MAE** (maximum favorable/adverse excursion) — requires intraday/daily price-bar
  history for each trade's holding period, which Trading212's API doesn't expose. Needs a
  market-data provider (planned for the watchlist/charting phase).
- **Performance by "setup"** — Trading212 has no concept of trade setups/strategies; this
  needs a manually-tagged trade journal, which belongs to the future portfolio-coaching phase.
- **XIRR / money-weighted return and cash-flow-aware metrics** — would require syncing
  `/history/transactions` (deposits/withdrawals). Nothing in this iteration's metric list
  needs it, so it's deferred rather than built speculatively.
- **Date-range filtering** — all metrics are all-time for this iteration. A date-range picker
  can be added later once it's clear which windows are actually useful (YTD, last 90 days,
  etc.).

## Architecture

Three new pieces, following the existing `snapshot.py` / `scheduler.py` pattern:

- **`Trading212Client`** — two new methods:
  - `get_historical_orders(cursor: str | None) -> dict` wrapping `GET /equity/history/orders`
  - `get_dividends(cursor: str | None) -> dict` wrapping `GET /equity/history/dividends`

  Both endpoints are paginated (cursor-based); each call returns one page plus a
  next-page cursor.

- **`services/history_sync.py`** — a new scheduled job, registered alongside the existing
  snapshot job in `scheduler.py`. On each run it pages through order/dividend history
  *newest-first* and stops as soon as it reaches an id already present in the corresponding
  table. This makes the first run a full backfill and every run after that a cheap
  incremental sync (only fetches pages containing fills/dividends newer than the last sync).

- **`services/metrics.py`** — pure functions, no I/O. Takes already-loaded `OrderFill` /
  `Dividend` / `PortfolioSnapshot` rows and returns computed metrics. Kept free of DB/HTTP
  dependencies so trade-matching and every metric formula can be unit-tested against
  hand-built fixture data without touching a database.

## Data model

Two new tables, populated only by the sync job (raw fill/dividend data — nothing
pre-aggregated or derived is stored):

**`order_fills`**
| column | type | notes |
|---|---|---|
| `id` | String, PK | Trading212's own order id — used as the idempotency/dedup key |
| `ticker` | String | |
| `direction` | String | `BUY` or `SELL` |
| `quantity` | Float | |
| `fill_price` | Float | |
| `filled_value` | Float | |
| `currency` | String(3) | |
| `fees` | Float | sum of any taxes/charges Trading212 reports on the fill |
| `filled_at` | DateTime (tz-aware) | |

**`dividends`**
| column | type | notes |
|---|---|---|
| `id` | String, PK | Trading212's own dividend id |
| `ticker` | String | |
| `amount` | Float | |
| `currency` | String(3) | |
| `paid_at` | DateTime (tz-aware) | |

Metrics are computed **on read**, inside the new API endpoint, from these raw rows — not
cached or pre-aggregated. At single-user, hundreds-of-trades scale this is fast enough
in-process and avoids inventing cache-invalidation logic for a derived table.

## Trade reconstruction: FIFO matching

Trading212's history API returns individual fills, not "trades." A trade — in the sense
needed for win rate, holding period, expectancy, etc. — only exists once a sell fill is
matched against the buy fill(s) that opened the position.

This design uses **FIFO matching**: each sell closes out the *oldest* open buy lot(s) first,
producing discrete closed-trade records (ticker, entry date/price, exit date/price, quantity,
realized P&L, fees). This is deliberately different from Trading212's own accounting, which
uses average cost (visible as `averagePricePaid` on open positions) — average cost doesn't
produce well-defined discrete trades when a position is scaled into/out of over multiple
fills, so it can't drive per-trade stats like holding period. FIFO can. As a result, the
computed total realized P&L may not match Trading212's own `account.realizedProfitLoss`
figure exactly; both are surfaced so the discrepancy (if any) is visible rather than hidden.

A sell fill may partially close multiple buy lots (or a buy lot may be split across multiple
future sells); the matcher handles partial-lot consumption.

## Metrics (v1, all-time)

**From FIFO-matched closed trades:**
- Realized P&L — total, and broken down by ticker
- Win rate
- Average winning trade / average losing trade
- Expectancy (`win% × avg_win − loss% × avg_loss`)
- Profit factor (`gross profit / gross loss`)
- Payoff ratio (`avg win / avg loss`)
- Average holding period (time between entry and exit)
- Best trade / worst trade (by realized P&L)
- Current streak and longest streak (wins and losses)
- Closed trade count
- Entry/exit timing — **descriptive only**: distribution of entries and exits by day-of-week
  and time-of-day. (Comparing entries/exits against the day's intraday price range is a form
  of MFE/MAE and is out of scope for the reason stated above.)

**From existing `portfolio_snapshots` (no new data needed):**
- Max drawdown (largest peak-to-trough decline in the stored equity-curve series)

**From the `dividends` table:**
- Dividend income — total, and broken down by ticker

**From the live account summary (no sync needed):**
- Cash drag — `cash.availableToTrade / totalValue`

## API

New endpoint: `GET /api/portfolio/metrics`, same auth (`require_api_key`) as the existing
portfolio routes. Returns one payload containing all metrics above — total P&L/win-rate/etc.
figures, the by-ticker breakdown, and the entry/exit timing distribution. Reads `order_fills`,
`dividends`, and `portfolio_snapshots` from the DB, plus a live call to
`get_account_summary()` for cash drag; no other live Trading212 calls (history is served from
the synced tables, not fetched per-request).

## Frontend

New `PerformanceMetrics` component (or small set of components — a stats grid plus a
by-ticker table), added as a new "Performance" section on the existing dashboard page
(`app/page.tsx`), below "Open positions." Fetches from `GET /api/portfolio/metrics` the same
way the page already fetches current/history data. `lib/types.ts` gets the matching TypeScript
types for the new response shape.

## Testing

TDD throughout, matching the existing codebase pattern:
- `services/metrics.py` — unit tests for FIFO matching and every metric formula, against
  hand-built fixture fills with known expected results (specific win rate, expectancy,
  streaks, etc.)
- `services/history_sync.py` — tested with a mocked `Trading212Client` (respx), covering
  first-run full backfill and incremental (stop-at-known-id) behavior
- New router endpoint — request tests matching the existing `test_portfolio_router.py` pattern
- New frontend component(s) — Vitest + Testing Library render tests matching the existing
  `PortfolioSummary`/`PositionsTable` test pattern

## Open questions / risks

- The exact JSON shape of Trading212's `/equity/history/orders` and `/equity/history/dividends`
  responses (field names for fees/taxes, pagination cursor mechanics) isn't confirmed against
  live data yet — the implementation plan should pull a real response (or the official API
  docs) before finalizing field mappings, the same way `get_positions()`/`get_account_summary()`
  were built against real response shapes in phase 1.
