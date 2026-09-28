# Nectar Chain — v2.7.7 Bug-Fix Report

| ID | Issue | Repair |
|---|---|---|
| BUG-H20-R | SQLite reset/file replacement could race active Windows requests | In-place transactional reset; no DB-file deletion |
| BUG-H21-R | `/qr/<id>` route could ignore configured deployment base URL | Unified `current_base_url()` usage |
| BUG-R22 | `Reload demo data` button existed but had no event handler | Full frontend reset/reload handler added |
| BUG-R23 | Reset helper functions/state existed but were never invoked | Reset now clears UI state, verification cache and event log |
| SEC-R24 | Demo-only destructive endpoints had no deployment switch | Added `NECTAR_DEMO_MODE` guard |

## UI retained

- registration success/failure is a temporary toast
- demo-harvest action no longer truncates the newly registered Hive ID
- verification tick uses high-contrast styling
- consumer numeric indicator is labelled Evidence completeness
- alert refresh provides feedback and locks while active
