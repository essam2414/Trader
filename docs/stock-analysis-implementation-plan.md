# Stock analysis and stock-specific news

Approved scope: long positions held for 2–10 trading days. The expanded watchlist
chart gets an Analysis / News switcher. Trading212 remains read-only.

## Implementation sequence

1. Add typed analysis responses and a durable latest-snapshot table, with an
   idempotent Alembic migration. Keep decimal arithmetic inside the calculations.
2. Implement daily EMA20, SMA50, RSI14, ATR14/ATR%, ADX14 with directional
   indicators, and 5/20-session price-return differences versus SPY. Add current
   distances to averages, extension in ATR units, previous-20-session high/low
   distances, and cumulative same-time regular-session RVOL20.
3. Add an analysis module that owns calendar-aware data fetching, bounded caches,
   snapshot persistence, freshness and provider failures. Use split-adjusted SIP
   daily bars (250 completed sessions where available) and five-minute bars for
   comparable regular-session volume. Never mix IEX volume into SIP calculations.
4. Register a five-minute background refresh for all watchlist stocks, startup
   catch-up, and initial refresh when adding a stock. Daily inputs change after
   the actual exchange close plus 20 minutes and are rechecked before the next
   session. Intraday inputs use only fully elapsed bars at least 15 minutes old.
   Shared SPY/calendar data are cached. No market-data fetching on every UI render.
5. Add authenticated GET /api/watchlist/{asset_id}/analysis and a Next.js proxy.
   Cached responses render immediately; background work repairs stale or missing
   snapshots. Return explicit loading, unavailable, partial and stale states.
6. Extend GET /api/news with an optional assetId filter before offset/limit. Pass
   the filter through the authenticated Next.js proxy. Reuse stored stories and
   the existing detail dialog, including date uncertainty and pending summaries.
7. Build a bounded right-hand pane with accessible tabs, numeric metric rows,
   green/bullish, red/bearish and white/neutral states, and click/keyboard info
   explanations. Keep daily and intraday timestamps visible. News uses a single
   column, pagination, and 30-second visible-tab polling. Analysis checks cached
   results periodically and when the tab becomes visible.
8. Verify calculations with reference/hand-calculated cases, threshold boundaries,
   calendar early closes and holidays, missing bars, zero volume, short histories,
   splits, shared benchmark caching, snapshot fallback, per-stock pagination,
   tab changes and accessible explanations. Run focused tests, repository checks,
   then browser validation at desktop widths.

## Interpretation rules

- Trend: bullish when the available regular-session price is above EMA20 and
  SMA50 and both averages rise over five sessions; bearish for the converse;
  otherwise mixed/neutral. Outside a forming session, use the settled daily close.
- RSI: below 40 is weak/bearish; above 50 is upward/bullish momentum; 40–50
  neutral. Above 70 adds an overbought warning without implying a reversal.
  Below 30 adds an oversold warning without implying a buying opportunity.
  Equal average gains/losses produce neutral RSI 50, including a flat history.
- RVOL: at least 1.5 times comparable volume supports a rise or cautions on a
  decline versus the previous close. Other readings are neutral. Require 20
  comparable sessions and meaningful volume; missing data is not zero volume.
- ATR: volatility has no direction and remains white. ATR% above its prior
  126-session 90th percentile is labelled unusually volatile. A short history can
  display ATR without pretending a percentile is available.
- Range: previous 20 sessions exclude the assessed session. Below the low is a
  bearish breakdown; within 0.5 ATR below the high is near resistance (neutral);
  above the high with RVOL at least 1.5 is a bullish breakout context.
- Relative strength: stock price return minus SPY price return, in percentage
  points, on exactly matching dates. Green requires outperformance and a positive
  absolute stock return; red requires underperformance and a negative absolute
  stock return. Mixed readings stay white. Show both returns next to the spread.
- ADX: at least 25 with +DI above -DI is an established upward trend; reverse
  direction is caution; under 20 is weak and 20–25 developing/neutral.
- Extension: more than +2 ATR above EMA20 is stretched, but remains white because
  extension alone does not establish direction. No universal favourable volatility
  or distance is asserted. These thresholds are descriptive defaults, not a
  backtested probability of profit. Colours describe evidence, not predictions.

## Data and operational details

Use the exchange calendar for session dates, DST and early closes. Native daily
bars supply price indicators; RVOL uses regular-session intraday bars consistently
because daily volume can contain extended hours. Exclude forming daily candles.
Cache daily inputs through the next close/recheck and intraday inputs through the
next five-minute cutoff. Re-fetch the adjustment window on each new daily input
cycle so stock splits and provider corrections are reflected. Missing recent
sessions invalidate freshness; missing interior sessions limit usable history.
No fabricated bars, zero-filled prices, inferred earnings dates or profit score.
Use the settled native daily close after publication rather than the last
five-minute close, which can omit the closing auction. Retry incomplete intraday
coverage even when the market is closed and the cutoff remains unchanged.
Version persisted calculations so corrected formula/interpretation rules rebuild
older snapshots immediately instead of showing them as current.

The backend must be running for scheduled work. After outages, keep the last
successful snapshot visibly stale and retry. Opening or switching News only reads
the existing pipeline; collection retains its current schedule. Reward/risk trade
planning with user-supplied entry, stop and target remains a later feature.

## References

- [Fidelity EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema)
- [Fidelity RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI)
- [Fidelity ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr)
- [Fidelity ADX](https://www.fidelity.com/viewpoints/active-investor/average-directional-index-ADX)
- [TradingView relative volume at time](https://www.tradingview.com/support/solutions/43000705489-relative-volume-at-time/)
- [Alpaca bars](https://docs.alpaca.markets/us/reference/stockbars)
- [Alpaca feed and aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq)
- [TA-Lib independent indicator implementation](https://ta-lib.github.io/ta-lib-python/)
- [TA-Lib directional-movement initialization](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_ADX.c)

## Completion record

Completed:

- Backend calculations, persisted snapshots, five-minute scheduler/startup catch-up,
  authenticated analysis route, and stock-filtered news pagination implemented.
- Frontend tabs, 11 metric rows across the approved groups, click/keyboard help,
  directional colours, stale/partial states, visible-tab polling and news details
  implemented. The chart's selected range does not change daily indicator periods.
- 296 backend tests and 127 frontend tests passed. Ruff lint/format, frontend lint,
  TypeScript and the production build passed.
- Applied revision `20261004_stock_analysis`. The existing local runtime currently
  configures SQLite through DATABASE_URL; this work follows that setting and uses
  SQLAlchemy/Alembic types compatible with PostgreSQL. Database conversion was not
  part of this feature, and PostgreSQL runtime validation was not performed.
- Restarted stalled local development servers; all 12 watchlist entries received
  saved snapshots. Sandisk returned a ready analysis with all 11 metric rows.
  Eleven stocks had full history; FPS had 166 sessions and still displayed all
  metrics, with a shorter-history notice. An additional regression check verifies
  that this notice does not claim available readings are missing.
- Playwright verified real Sandisk news and source links, information disclosure
  and Escape behaviour, chart-range independence, scrolling to the final metric,
  and no horizontal overflow at 1024px. Screenshots are local validation artifacts
  under `output/playwright/`.

## Calculation audit — 2026-10-04

Compared all 12 current watchlist stocks with TA-Lib Python 0.6.8 (C library
0.6.4), using the same split-adjusted SIP inputs. EMA20, SMA50, RSI14, ATR14,
ADX14 and both DI values were checked against the independent implementation.
Separate calculations checked the two SPY return spreads, same-time RVOL,
extension and prior range references. All 156 comparisons passed; the largest
absolute difference after correction was approximately 6.83e-13.

Corrections from the audit:

- ADX/DI now initialize from 13 directional differences, followed by a Wilder
  update on difference 14, matching the reference convention. The old seed had
  a visible effect on short histories (about 0.49 ADX points at 28 observations
  in the synthetic fixture); the difference was negligible with 250 observations.
- RSI above 70, unusually high ATR, extension and proximity to resistance are
  no longer automatically treated as bearish. Relative performance considers
  the stock's absolute return before assigning a directional colour.
- Settled closing-auction prices take precedence over the final intraday bucket.
- Incomplete volume history is re-fetched on retry, and saved calculations have
  a version marker so older interpretations are not served as current results.

Regression fixtures pin independent numbers at 15, 20, 28, 50, 166 and 250
observations without adding TA-Lib as an application/test dependency. Existing
calendar, missing-data, zero-volume and same-date benchmark tests remain in
place. The intentional neutral RSI value of 50 for an entirely flat series is
documented; libraries differ on that mathematically undefined 0/0 case.

This verifies the arithmetic and documented assumptions. The 40/50 RSI bands,
1.5× volume threshold, 2 ATR extension and 0.5 ATR resistance distance are
descriptive defaults, not empirically validated forecasts for these stocks.

Validation after the corrections: 314 backend tests and 10 focused frontend
tests passed, along with Ruff lint/format, frontend lint and TypeScript checks.
The existing API returned healthy/ready responses. A browser check confirmed
actual green RSI, red five-session relative performance and white ATR values
in Sandisk's pane; screenshot: `output/playwright/stock-analysis-audited.png`.
