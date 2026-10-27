# News pipeline implementation plan

## Goals

- Show one card for one stock-specific catalyst, with all supporting source links attached.
- Keep publication dates separate from dates when the article says the catalyst happened.
- Make undated cards easy to inspect without allowing an unverified date to look verified.
- Refresh the visible news list shortly after a scheduled collection completes.

## Phases

1. **Analyst-event identity and reconciliation**
   - Use one stock-specific identity for analyst coverage and price-target actions.
   - Normalize known firm aliases, action verbs, and target values; read the publisher title and relevant excerpt.
   - Require matching stock, firm, action, and new target before merging target-change stories. Keep different firms and target values separate.
   - Run the same reconciliation before and after collection so existing cards and newly fetched items are handled.
   - Reconcile the observed AMD $720 cards into one visible card while retaining every source and merge audit row.

2. **Date evidence and precision**
   - First use publisher metadata and structured article metadata.
   - Also inspect visible article text for explicitly labelled publication dates such as “Published on …”. Preserve date-only precision rather than inventing a time.
   - Treat dates that appear in catalyst wording as a separate event date. Do not copy an event date into `released_at`; expose it with its own label and use it only where it is supported by the article text.
   - Keep blocked, missing, and inferred date reasons visible in source details. Do not bypass publisher access controls.

3. **Verified and unverified views**
   - Add a toggle beside the collection-error indicator, defaulting to Verified.
   - Verified shows cards with a verified publication date; Unverified shows cards without one. Toggling returns to the other set.
   - Keep first-found time visible for undated cards.

4. **Scheduled-run visibility**
   - Observe completed collection run timestamps through the lightweight news-status route.
   - Reload cards as soon as the run ID changes while the dashboard is visible, without waiting for the existing five-minute refresh interval.

5. **Validation**
   - Cover the AMD source/title variants, different firms and target values, labelled body publication dates, event dates that must not be treated as publication dates, filtering, and completion refresh behavior.
   - Review migration behavior and run relevant backend/frontend checks before calling the change complete.

## Progress

- Implemented stock/firm/action/target matching for analyst target changes and run reconciliation before and after source collection.
- Added body-text parsing for explicitly labelled publication dates and catalyst dates. Catalyst dates remain separate from publication dates; date-only releases retain date-only precision.
- Added the Verified/Unverified view and a 10-second completed-run status check that reloads cards when the run timestamp changes.
- Applied the additive date-precision/event-date migration and merged the three stored AMD $720 cards into one visible card with all three sources retained.
- Python compilation, focused Ruff checks/format, frontend lint, and migration state checks pass. Regression fixtures and full test runs remain outstanding.
