# News analysis reliability implementation plan

## Problem and acceptance criteria

Manual collection succeeds while analysis remains blocked. The observed queue contains
15 hidden developments and one published story awaiting an updated summary. Seven
attempts failed numeric validation and nine failed coverage comparison. Equivalent
numeric formatting is rejected; comparison errors lose their cause; every failure
uses the same retry policy and the UI describes all outstanding work as summaries.

The implementation must accept equivalent source-backed numbers without accepting
changed currency, magnitude or percentages; preserve the reason for held coverage;
avoid repeating completed comparison batches; bound retries for unchanged evidence;
and explain the queue and manual-refresh outcome. Publication timestamps and all
portfolio, fee, tax, FX and trading behaviour remain unchanged.

## Implementation sequence

1. Add regressions at the actual summariser and coverage-comparison interfaces.
   Normalise numbers with Decimal, currency and unit information, validate against
   cited sources, and allow one evidence-constrained corrective response.
2. Preserve typed comparison failures and tolerate whitespace-only quote changes.
   Cache successful batches using model/rule version and complete input hashes.
   Never cache ambiguous or failed decisions as completed comparisons.
3. Persist analysis failure kind, consecutive failure count and input hash. Use
   backoff for temporary failures; hold repeated validation/ambiguity failures for
   review after three attempts. Changed evidence/history/model resets the hold.
   Manual refresh explicitly retries held items. Existing published summaries stay
   visible while replacement summaries are checked.
4. Return mutually exclusive queue counts and source links for blocked evidence;
   show separate waiting, validation, comparison and review statuses. Manual refresh
   reports analysis attempts, resolved items and remaining work separately from
   source collection. Keep the existing aggregate fields compatible.
5. Add an idempotent migration, run focused and relevant full checks, apply the
   migration locally and retry the stored backlog through the same checked path.
   Record actual remaining blockers rather than force publication.

## Verification

- Summariser tests: $60.000B/$60B, grouped share counts, implicit US-dollar SEC
  per-share prices, changed magnitude/currency/percent, cited evidence and bounded
  corrective attempts.
- Comparison tests: whitespace equivalence, invented quotes, specific transport,
  budget and ambiguous failures, completed-batch reuse and hash invalidation.
- Queue tests: backoff, three-attempt hold, changed evidence/history recovery,
  manual retry, preservation of existing published summaries and status totals.
- Migration round trip and API/frontend contract tests, frontend lint/tests/build,
  backend pytest and Ruff. Do not overwrite unrelated stock-analysis work.

## Limits

Numeric normalisation establishes numerical equivalence within cited evidence; it
does not independently prove the semantic attribution of every sentence. Novelty
checks retain their requirement to compare all relevant history and cite evidence.
Insufficient or ambiguous source material remains held with an actionable reason.

## Implementation and local verification

Implemented the numeric validator, bounded summary/quote correction, comparison
cache, persisted retry policy, disjoint status counts, evidence links and visible
refresh outcome. Applied revision `20261006_news_analysis` to the existing local
database; a database backup is under `output/`.

The full backend suite passed (338 tests at that checkpoint); subsequent focused
regressions also passed. The full frontend suite passed (132 tests), with final
refresh-output coverage checked again alongside lint/build. Ruff checks passed.

Live verification cleared 11 of the original 16 outstanding items. The final manual
refresh returned HTTP 200: 30 sources collected successfully, 8 analysis attempts,
3 resolutions and 5 items remaining. The remaining evidence has multiple plausible
prior matches or rejected quotes and stays unpublished. Micron web search returned
HTTP 429 separately; its existing source cooldown remains active.

Authenticated Playwright validation requires explicit permission to use the local
PIN: automatic approval review rejected reading and using it from source. Browser
login was not performed; component tests and the production build cover the UI.
