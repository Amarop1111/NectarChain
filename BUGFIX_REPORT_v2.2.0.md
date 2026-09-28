# Nectar Chain v2.2.0 — Bug Fix Report

## Bugs found in the provided latest prototype

### 1. Successful hive registration could appear to fail
The registration POST could succeed, but the subsequent dashboard refresh used one `Promise.all()` across hives, batches, alerts and summary. A failure in any one of those requests caused the entire refresh to abort, so the newly registered hive was not rendered.

**Fix:** registration now inserts the returned hive into the UI immediately, and dashboard sections refresh independently.

### 2. Legacy databases could break the dashboard with HTTP 500
The database migration covered newer batch fields but did not guarantee newer hive/reading/evidence/alert columns needed by the current code.

**Fix:** expanded schema migration for legacy SQLite databases.

### 3. Repeated “Run demo harvest” could produce HTTP 500
The deterministic demo keeps subtracting approximately 6 kg from HIVE-001. After enough clicks, its synthetic weight became non-positive and `process_iot_reading()` raised an uncaught `ValueError`.

**Fix:** the endpoint now detects depletion and returns a controlled HTTP 409 with an actionable reload-demo message. The UI also disables the button during execution.

### 4. Registration could still return HTTP 500 after the database insert
Even after committing the new hive, the API response calculated a health summary. A health-summary problem could therefore make a successfully inserted hive look like a failed registration.

**Fix:** registration response now safely returns the created record with an `unknown` health state if health-summary calculation fails.

### 5. A single bad hive/batch could blank a whole dashboard section
List APIs previously enriched every row without a per-row recovery path.

**Fix:** `/api/hives` and `/api/batches` now preserve usable records and expose a diagnostic field for the affected row instead of failing the whole list.

### 6. Weak input handling on hive registration
Whitespace-only values could reach the server, and duplicate IDs produced a generic conflict message.

**Fix:** server-side trimming, required-field validation, Hive ID length validation, and clearer duplicate-ID errors.

## Additional hardening

- Automatic database initialization/migration when `app.py` is imported, which is safer for test/WSGI-style execution.
- Dashboard refresh preserves the last known state when a transient API failure occurs.
- Register and demo-harvest buttons are disabled while their requests are in flight.
- `self_test.py` now covers registration success, duplicate rejection, invalid registration, and repeated demo-harvest safety.
