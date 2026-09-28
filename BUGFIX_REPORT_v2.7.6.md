# Nectar Chain — v2.7.6 Bug-Fix Report

## Confirmed regressions repaired

| ID | Issue | Repair |
|---|---|---|
| BUG-H17 | Double-click demo harvest created HC-0004 + HC-0005 | Backend idempotency window + action lock |
| BUG-H19 | Double-click Validate & commit duplicated review events | Immediate per-batch action lock |
| BUG-H20 | `/api/hives` HTTP 500 from SQLite `database is locked` | Connection timeout, busy timeout, one-time WAL setup, safe reset sequencing |
| BUG-H21 | QR encoded `127.0.0.1` | Configurable `HONEYCHAIN_BASE_URL`; request-host-aware QR generation |

## UI cleanup completed

| ID | Issue | Repair |
|---|---|---|
| UI-01 | Demo-harvest quick action truncated Hive ID | Responsive width / no truncation |
| UI-02 | Verification tick lacked clear contrast | Explicit high-contrast icon treatment |
| UI-03 | Evidence score could be mistaken for integrity score | Renamed to Evidence completeness |
| UI-04 | Registration confirmation stayed visible | Temporary toast |
| UI-05 | Stale selected-hive/action state after reset | Reset UI state explicitly |
| UI-06 | Historical event log survived demo reset | Clear event log on reset |
| UI-07 | Double-click could trigger second action | Immediate action locking |
| UI-08 | Alert refresh had no visible feedback | Refresh locking + event feedback |

## Intentionally not changed

- The prototype remains a local SQLite cryptographic hash-chain trust layer, not a decentralized blockchain network.
- AI disease output remains screening/decision support, not diagnosis.
- Demo camera evidence remains explicitly synthetic.
- `HONEYCHAIN_BASE_URL` remains an environment variable so deployment can define the reachable public URL.
