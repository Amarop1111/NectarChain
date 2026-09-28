# Nectar Chain v2.2.0 — Regression Fixes

## Fixed

1. **Hive registration appeared to fail after a successful POST**
   - The dashboard previously depended on four API calls succeeding inside one `Promise.all()` refresh.
   - A failure in `/api/batches`, `/api/health-alerts`, `/api/summary`, or `/api/hives` could hide a successful registration.
   - Registration now updates the hive list immediately and the dashboard refreshes each data source independently.

2. **Repeated demo harvest could throw HTTP 500**
   - The deterministic demo eventually depleted HIVE-001 below the positive-weight constraint.
   - The route now returns a controlled HTTP 409 with an actionable message instead of an uncaught exception.

3. **Legacy database migration gaps**
   - Added defensive migrations for hive, reading, AI result, evidence, and alert columns used by the upgraded dashboard.
   - This prevents older `honeychain.db` files from breaking dashboard APIs after an upgrade.

4. **Per-record dashboard resilience**
   - A malformed legacy hive/batch no longer blanks the entire list response.
   - The affected record is returned with an explicit `health.error` or `api_error` field.

5. **Registration validation**
   - Server strips whitespace, rejects empty values, and rejects overlong hive IDs.
   - The UI validates all five fields before sending and shows actionable failure messages.

6. **Button-state hardening**
   - Register and demo-harvest buttons are disabled while requests are in flight to avoid accidental duplicate submissions.

7. **Registration response hardening**
   - A successful database insert is no longer converted into HTTP 500 merely because health-summary calculation fails.

## Version

Prototype version: **2.2.0**
