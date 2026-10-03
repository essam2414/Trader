# News pipeline repair

## October 4 implementation: durable development identity

The runtime uses `news_resolution.py` for ingestion, scheduled/manual collection,
pending-summary retries and database repair. The earlier headline reconciliation
helpers remain available for historical tests, but are no longer a publication step.

- `news_source_items` retains distinct content revisions instead of overwriting an
  article's earlier evidence. Provider IDs and exact content still prevent replays.
- `news_event_identities` persists unique aliases independently of the seven-day
  collection window. Structured identities distinguish fiscal year/quarter and
  earnings phase, analyst actions, and capacity-project qualifiers. Missing anchors
  can attach to one compatible reporting window; conflicting or ambiguous projects
  cannot be joined through a partial description. Generated categories are not keys.
- `news_resolution_decisions` records the evidence hash, rule version, outcome,
  reason and matched card. Semantic matches also retain their evidence quotes.
- Unknown candidates with prior coverage use `resolving`, which is not returned by
  the news feed or detail endpoint. The existing configured OpenAI news service
  compares all relevant history in batches of twelve, under the same daily budget.
  New facts can produce a linked material update; rewordings attach to the original.
  Unavailable or ambiguous comparisons remain hidden and retry with a status notice.
- Consolidation preserves sources, stock associations, original discovery time,
  aliases and merged-row history. Summaries awaiting regeneration retain their last
  usable text and are marked dirty. Summarisation never advances release order.
- `news_dates.py` chooses the earliest verified reporting date, preferring known
  clock precision on that day. Earlier same-day times are accepted. Discovery and
  update timestamps are not substituted for an unknown release time. API ordering
  applies before pagination, uses explicit null placement, and matches the frontend.

Apply the additive migration before starting the updated backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.services.news_resolution
```

The last command is a read-only preview. After reviewing its output and taking a
database backup, `python -m app.services.news_resolution --apply` applies the same
rules. A second preview should report no merges or date corrections. The normal
pending-summary job refreshes dirty summaries using the existing configured AI
service; it does not fetch new news. Original release times must be treated as
the earliest verified evidence available, not proof of the first-ever publication.

Regression fixtures include the stored Toshiba expansion articles and Micron Q4
results. Coverage exercises reversed arrival order, delayed replays, different
fiscal periods/phases/projects, semantic failure, same-URL revisions, source quote
validation, rate limits, date precision, migration and API pagination.

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
