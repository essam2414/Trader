# Trader domain glossary

## Watchlist Entry

A locally saved, read-only reference to one supported US equity. It identifies
the instrument to present; it is not a position, trade, or recommendation.

## Price Bar

A durable OHLCV observation for one watchlist instrument over one stated time
interval, with the time interval's opening timestamp and market-data
provenance. A provider correction may supersede an earlier observation with
the same instrument, interval, and opening timestamp.

## Raw Price Bar

A Price Bar as reported by its source with no price adjustment applied. It is
the durable market-data observation from which adjusted views may be produced.

## Adjusted Price Series

A reproducible view derived from Raw Price Bars and recorded corporate actions
under a named adjustment policy, such as split-adjusted or total-return.

## Corporate Action

An issuer event, such as a split, dividend, spin-off, merger, or symbol
change, that can affect an instrument's identity, holdings, or interpretation
of its historical prices.

## Chart Range

A viewer-selected historical period for a Watchlist Entry. A range determines
which Price Bars are displayed; it does not change or create Price Bars.

## Canonical Price Series

The one consistently sourced and adjusted series used for historical analysis
and settled chart bars. A provisional observation never changes its provenance
or becomes Canonical merely by being displayed beside it.

## Provisional Price Tail

The most recent, not-yet-canonical part of a chart. It may be replaced when
the Canonical Price Series becomes available and must remain visibly distinct
from it.

## Regular Hours

The exchange's scheduled primary US equity trading session, including its
calendar-specific opening and closing times.

## Extended Hours

Eligible pre-market and after-hours trading outside Regular Hours. It is
distinct from overnight trading and may contain no trades for an interval.
