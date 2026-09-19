# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is currently a bare scaffold: only this file and `README.md` exist, no
application code has been written yet. There are no build, lint, or test commands to run —
these will need to be established as part of initial implementation, and this file should be
updated once they exist.

## What this project is

"Trader" is a swing-trading decision-support app — explicitly **not** an auto-trader — for a
solo user who trades a watchlist of AI hyperscaler stocks on Trading212. Its purpose is to
automate the research/monitoring work a swing trader does manually: tracking company news,
sector news, and macro/geopolitical events; eyeballing support/resistance; and reviewing past
trades for mistakes. Planned capabilities:

- Read-only portfolio dashboard synced from the Trading212 API
- A manually-curated watchlist with relevant news surfaced per stock
- Price charts with computed technical indicators (support/resistance at daily/monthly/yearly
  granularity, plus others to be chosen once real data is visible)
- An LLM-driven "opportunity score" per watchlist stock, combining news, macro/geopolitical
  context, and technicals
- Portfolio coaching: LLM analysis of the user's own Trading212 order history to surface
  mistakes and improvement tips
- Eventually, push notifications (web push / PWA) to a phone

## Intended architecture

Decided during initial architecture brainstorming (not yet implemented — update this section as
real code establishes the actual structure):

- **Frontend**: Next.js (React + TypeScript) + Tailwind, `lightweight-charts` for price charts,
  deployed on Vercel
- **Backend**: Python FastAPI, deployed on Railway/Render, `APScheduler` for periodic
  portfolio-sync and news-ingest jobs (no task queue needed at this scale)
- **Database**: Postgres + `pgvector` via Supabase (also provides auth) — one store for
  relational data (positions, watchlist, order history) and RAG embeddings
- **AI**: Anthropic Claude API for news summarization, opportunity scoring, and portfolio
  coaching
- **External data sources**:
  - Trading212 API (beta, read-only use only — positions, cash, order/dividend history; Invest
    and Stocks ISA accounts only, no CFD; does **not** provide general OHLCV price history)
  - Alpaca Market Data API (price history + news; user already has an account)
  - Finnhub (earnings calendar, sentiment)
  - FRED (macro/economic data)

Planned build order: Trading212 sync + dashboard → watchlist + news feed → charting +
indicators → RAG-based opportunity scoring → portfolio coaching → push notifications.

Scope is single-user for now; the schema/design should avoid blocking multi-tenancy later (e.g.
via Supabase Row-Level Security) without building full multi-tenant auth up front.
