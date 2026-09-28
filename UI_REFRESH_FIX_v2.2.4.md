# UI Refresh Fix v2.2.4

## Fixed
- Manual Refresh now has explicit visible feedback: `Refreshing…` while active and `Updated <time>` after success.
- Successful manual refresh writes a `Dashboard refreshed` event to the dashboard event log.
- Refresh failures/warnings are surfaced instead of failing silently.
- Refresh state is always released in a `finally` block, so one failed request cannot permanently disable the button.
- Concurrent manual refresh clicks are safely ignored with a clear `Refresh skipped` message.
- The dashboard still has no timer-based refresh loop; refresh remains user-triggered.
- The Refresh button is explicitly `type="button"`.

## Expected behavior
- Opening the dashboard loads data once.
- Waiting does not trigger automatic reloads.
- Clicking Refresh changes the button to `Refreshing…`, then shows `Updated <time>` and logs `Dashboard refreshed`.
- If an API fails, the UI reports the warning/failure and the button remains usable.
