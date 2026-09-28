# Nectar Chain v2.2.4 — Refresh UX / Reliability Fix

## User-reported bug
Clicking the dashboard **Refresh** button appeared to do nothing, even though the prototype had already been changed to remove the automatic refresh timer.

## Root cause
The manual refresh path performed the API reload silently. When the returned values were unchanged, there was no persistent visual confirmation that the click had completed. In addition, the previous refresh guard could remain engaged if an unexpected exception escaped before the state was released.

## Fixes in v2.2.4
- Manual Refresh now uses an explicit `manual` refresh mode.
- Button changes to `Refreshing…` while the request is active.
- A visible `refresh-status` label reports `Updating dashboard…`, then `Updated <time>` after success.
- A successful click adds a `Dashboard refreshed` entry to the event log.
- Partial API failures are surfaced as `Dashboard refresh warning` instead of failing silently.
- Unexpected refresh failures are caught and reported as `Dashboard refresh failed`.
- Refresh state is released in `finally`, so the button cannot remain permanently locked by an exception.
- Concurrent manual clicks are rejected with `Refresh skipped` while the first refresh is still running.
- The Refresh button is explicitly `type="button"`.
- No automatic timer-based refresh was reintroduced; the dashboard only loads on initial page load and after explicit user actions.

## Validation performed
- JavaScript syntax check passed with `node --check static/js/app.js`.
- Python syntax checks passed for the application, seed script, self-test, AI modules and IoT simulator.
- Static source inspection confirms there is no `setInterval`, `setTimeout`, or `location.reload` refresh loop in the dashboard frontend.

## Expected manual test
1. Start the app.
2. Wait at least 60 seconds without touching the dashboard. No values should change by themselves.
3. Click **Refresh** once.
4. The button should visibly change to `Refreshing…` and the status should show `Updating dashboard…`.
5. After completion, the status should show `Updated <time>` and the event log should contain `Dashboard refreshed`.
6. Clicking Refresh repeatedly while a request is active should not create overlapping refresh requests.


## v2.2.5 validation hardening
- Registration now rejects whitespace-only and punctuation-only values.
- Hive IDs must match a safe 3–64 character format: letters/numbers with `-`/`_`.
- Added regression coverage for invalid registration values.
