# Trends ranking plan

## Goal

The Trends page keeps its manual chart order until the user presses **Trend**. That click ranks only the selected stocks by the strength of their current short-term upward price pattern and saves the resulting chart order. Changing the displayed chart range or receiving live trades never reranks charts.

## Data and score

Use the existing chart source once per stock with a dedicated 31-day daily-bar ranking range. Its split-adjusted delayed SIP daily closes contain both the latest trading week and the month context. Alpaca's daily trade rules exclude extended-hours trades from the daily close, including on early-close sessions. Do not request the provisional IEX tail: it is unnecessary for the score and must not make an otherwise valid SIP ranking fail. Report the date of the latest price bar as `asOf`; the daily bar has no exact close timestamp.

Require at least ten distinct trading-day closes, including five for the recent trend. Reject history whose latest bar is more than seven calendar days old. Insufficient or unavailable stocks remain visible, after ranked stocks, in their previous relative order.

For the most recent five closes, calculate the median of all pairwise log-price slopes (Theil–Sen). Convert the slope to a projected four-session percentage move. This makes a lone endpoint jump less influential than a sustained climb. Calculate recovery as the latest close above the lowest close in the one-month sample, and consistency as the fraction of the last four close-to-close moves that were positive.

Initial score, from 0 to 100:

`0.60 × clamp(weekTrendPercent / 10, 0, 1) × 100 + 0.25 × clamp(monthRecoveryPercent / 15, 0, 1) × 100 + 0.15 × consistency × 100`

Rank positive recent slopes before flat and negative slopes. Within the positive group, sort by score; within the nonpositive group, sort by signed slope, then score. Break ties by previous chart order. These weights are a descriptive starting point, not a prediction or a trading instruction.

## Implementation

1. Put the pure scoring and sorting logic in a backend module with a small interface for scoring a chart and comparing results.
2. Add an authenticated, read-only ranking route and a matching Next.js proxy. Fetch on button click only. Return per-stock status, score breakdown, and data timestamp.
3. Add the Trend button beside the shared range selector. Show progress and a concise result/error message. Apply and persist the new order only when at least one stock was scored. Keep manual reordering available afterward.
4. Verify steady rises, recoveries despite a negative monthly return, isolated spikes, falling recoveries, stale/missing data, route behaviour, and click-only frontend behaviour. Run relevant lint, formatting, tests, and build checks.

## Limits

The latest SIP observations are delayed. A ranking can change on the next click as new history arrives. The score compares price patterns, not expected returns, and is not a recommendation to trade.
