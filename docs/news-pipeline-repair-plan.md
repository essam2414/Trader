# News pipeline repair

## Outcome

One card represents one material development for a watched company. Manual refresh collects current evidence promptly, reports useful output separately from source health, and leaves a clear audit trail.

## Source portfolio

1. Keep SEC filings and working company investor-relations feeds as direct evidence. Keep one broad PR Newswire feed and one GlobeNewswire public-company feed; disable overlapping GlobeNewswire topic feeds and Bloom Energy's currently blocked feed. Keep Alpaca news as one Benzinga-backed reporting source.
2. Use OpenAI web search to find publisher links. Publisher metadata or other source text must substantiate a card; a generated search heading alone is a lead. Remove GDELT jobs until the endpoint has demonstrated reliable access and useful output. Finnhub remains optional and inactive without a configured key.
3. Count configured jobs, attempted jobs, useful items, and cards separately. Preserve source failures and cooldowns without making manual refresh retry providers that are still blocked.

For the current 12-stock watchlist this is 31 active jobs: five RSS feeds, 12 Alpaca ticker queries, one SEC job, one S&P archive job, and 12 web discoveries. Finnhub would add jobs only if explicitly configured.

## Card identity and existing data

1. Group exact URLs first, then use stock-specific event identity for earnings previews and analyst actions before relying on title similarity. Match against existing cards by the underlying event, including cards first seen more than seven days ago when the event is still current.
2. Resolve the existing Micron Q4 preview and Sandisk Rosenblatt duplicates into one visible card per event. Preserve links, stock associations, original timestamps, and merged-row audit history. Run the same conservative reconciliation after collection so future duplicates do not appear.
3. Keep genuinely different analyst firms, quarterly results versus an upcoming report, and unrelated company developments separate. Do not invent an earnings date when sources disagree.

## Refresh and interface

1. Fetch independent web discoveries with bounded concurrency, then ingest results in a deterministic order. Avoid reanalysing unchanged source records. Keep source collection independent of the browser tab.
2. Keep the last-run counts in the collection-error popup only. Show the indicator when a run has failures or deferred jobs, even if no unresolved source error remains.
3. Verify the Micron and Sandisk fixtures, the reduced job inventory, cooldown handling, useful-output counts, and the UI popup with focused tests, then run backend and frontend quality checks.
