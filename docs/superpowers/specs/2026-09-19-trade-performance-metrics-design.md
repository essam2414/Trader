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
  - `get_historical_orders(cursor: int | None, ticker: str | None) -> dict` wrapping
    `GET /equity/history/orders`
  - `get_dividends(cursor: int | None, ticker: str | None) -> dict` wrapping
    `GET /equity/history/dividends`

  Both endpoints are paginated (`items` + `nextPagePath`, max 50 items/page, 6 requests/60s
  rate limit); each call returns one page.

- **`services/history_sync.py`** — a new scheduled job, registered alongside the existing
  snapshot job in `scheduler.py`. On each run it walks every page (following `nextPagePath`
  until it's empty) and upserts rows keyed by id, doing nothing on conflict. The docs don't
  specify page ordering (newest-first vs. oldest-first), so the sync deliberately doesn't rely
  on an early-stop-at-known-id shortcut — it always walks the full history. At single-user,
  hundreds-of-fills scale this is a handful of pages, well within the rate limit for a job that
  runs every few hours (matching the existing snapshot job's cadence), so the simplicity is
  worth the small amount of extra API traffic.

- **`services/metrics.py`** — pure functions, no I/O. Takes already-loaded `OrderFill` /
  `Dividend` / `PortfolioSnapshot` rows and returns computed metrics. Kept free of DB/HTTP
  dependencies so trade-matching and every metric formula can be unit-tested against
  hand-built fixture data without touching a database.

## Confirmed API shapes

Pulled from the official docs (docs.trading212.com) rather than guessed:

- `GET /api/v0/equity/history/orders` — query params `cursor` (integer), `ticker`, `limit`
  (max 50). Response: `{items: [...], nextPagePath}`. Each item has nested `order` and `fill`
  objects. Relevant `fill` fields: `id`, `filledAt`, `quantity`, `price`, `type` (enum —
  `TRADE` for a normal buy/sell execution; other values are corporate actions: `STOCK_SPLIT`,
  `STOCK_DISTRIBUTION`, `SPIN_OFF`, `STOCK_DIVIDENDS`, etc.), `walletImpact` (`currency`,
  `netValue`, `realisedProfitLoss`, `taxes[]` — each tax entry has `name`, `quantity`,
  `currency`, `chargedAt`). Relevant `order` fields: `id`, `ticker`, `side` (`BUY`/`SELL`),
  `currency`, `instrument`.
- `GET /api/v0/equity/history/dividends` — query params `cursor` (integer), `ticker`, `limit`
  (max 50). Response: `{items: [...], nextPagePath}`. Each item: `amount` (already in the
  account's primary currency — no conversion needed), `currency`, `ticker`, `paidOn`, `type`
  (a large enum covering ordinary dividends, tax events, manufactured payments, etc.).

**Only fills with `fill.type == "TRADE"` represent an actual buy/sell execution** — corporate
actions (splits, stock dividends, spin-offs) also appear in this endpoint and must be
filtered out before FIFO matching, or they'd corrupt quantity/cost-basis reconstruction.

## Data model

Two new tables, populated only by the sync job (raw fill/dividend data — nothing
pre-aggregated or derived is stored):

**`order_fills`** (one row per `fill` where `type == "TRADE"`)
| column | type | maps from | notes |
|---|---|---|---|
| `id` | String, PK | `fill.id` | idempotency/dedup key |
| `order_id` | String | `order.id` | |
| `ticker` | String | `order.ticker` | |
| `side` | String | `order.side` | `BUY` or `SELL` |
| `quantity` | Float | `fill.quantity` | |
| `fill_price` | Float | `fill.price` | |
| `net_value` | Float | `fill.walletImpact.netValue` | in account currency |
| `realised_profit_loss` | Float | `fill.walletImpact.realisedProfitLoss` | Trading212's own per-fill realized P&L (0/absent on BUY fills); used as the cross-check total, see below |
| `fees` | Float | `sum(tax.quantity for tax in fill.walletImpact.taxes)` | |
| `currency` | String(3) | `fill.walletImpact.currency` | |
| `filled_at` | DateTime (tz-aware) | `fill.filledAt` | |

**`dividends`** (one row per item)
| column | type | maps from | notes |
|---|---|---|---|
| `id` | String, PK | derived — see implementation note below | |
| `ticker` | String | `ticker` | |
| `amount` | Float | `amount` | already in account currency |
| `currency` | String(3) | `currency` | |
| `type` | String | `type` | stored so dividend income can be filtered to genuine dividend types later if needed |
| `paid_at` | DateTime (tz-aware) | `paidOn` | |

*Implementation note:* the dividends endpoint doc doesn't show an `id` field on each item
(unlike orders/fills) — only a `reference` string. The implementation task must check a real
response and use `reference` as the dedup key if present, or fall back to a composite key
(`ticker` + `paidOn` + `amount`) if not. This is the one remaining schema uncertainty; resolve
it against a real account response as the first step of the sync-job task, before writing the
dedup logic.

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
uses average cost (visible as `averagePricePaid` on open positions, and as
`fill.walletImpact.realisedProfitLoss` on sell fills) — average cost doesn't produce
well-defined discrete trades when a position is scaled into/out of over multiple fills, so it
can't drive per-trade stats like holding period. FIFO can. As a result, the FIFO-computed P&L
per trade may not match Trading212's own `realisedProfitLoss` figure for the corresponding
sell fill exactly; **both are surfaced** — FIFO P&L drives all the per-trade stats (win
rate, expectancy, etc.), while `sum(realised_profit_loss)` across all sell fills is shown
alongside as "Trading212-reported realized P&L" so any discrepancy is visible rather than
hidden.

A sell fill may partially close multiple buy lots (or a buy lot may be split across multiple
future sells); the matcher handles partial-lot consumption.

## Metrics (v1, all-time)

**From FIFO-matched closed trades:**
- Realized P&L — total, and broken down by ticker (FIFO-computed)
- Trading212-reported realized P&L — `sum(realised_profit_loss)` across sell fills, shown
  alongside the FIFO figure as a cross-check
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
  multi-page pagination and idempotent upsert (running the sync twice doesn't duplicate rows)
- New router endpoint — request tests matching the existing `test_portfolio_router.py` pattern
- New frontend component(s) — Vitest + Testing Library render tests matching the existing
  `PortfolioSummary`/`PositionsTable` test pattern

## Open questions / risks

- **Resolved:** order/fill field names and pagination shape are confirmed against the official
  docs (docs.trading212.com) — see "Confirmed API shapes" above.
- **Still open:** the dividends endpoint doc doesn't show an explicit `id` field per item. The
  implementation must check a real account's response and pick the dedup key accordingly (see
  the implementation note under "Data model" above) before writing the upsert logic.
- **Still open:** the dividend `type` enum is large (70+ values spanning genuine dividends, tax
  events, and manufactured payments). For v1, "dividend income" sums `amount` across all
  types unless a real response makes it obvious that some types shouldn't count as income —
  worth a quick sanity check against real data during implementation, not a blocking decision.
