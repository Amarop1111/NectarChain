# Nectar Chain — Final Release Notes v2.7.6

## Scope
This release is the post-audit hardened prototype for SIH 26021.

The repair pass addresses the confirmed functional regressions and UI issues found during the browser acceptance test with the v2.7.5 build.

## Functional fixes

### BUG-H17 — duplicate demo harvest on rapid repeated click
Fixed.

The demo-harvest endpoint now uses an in-process concurrency guard plus a short idempotency window scoped to synthetic demo batches. A rapid second request for the same hive reuses the existing demo batch instead of creating a second HC record.

### BUG-H19 — duplicate validation events on rapid repeated click
Fixed at the UI action layer.

Validation actions are now immediately locked for the active batch. A rapid second click is ignored rather than submitting another request and generating a duplicate event entry.

### BUG-H20 — SQLite `database is locked` during demo reset / refresh
Fixed in the reset/connection path.

- SQLite connections use a 10-second timeout and `busy_timeout`.
- WAL mode is configured once during database initialization, not on every request connection.
- The demo-reset endpoint closes its current request connection before deleting/recreating the SQLite database.
- Demo reset is serialized inside the Flask process.
- SQLite WAL/SHM sidecar files are removed during a deterministic filesystem reset.

### BUG-H21 — QR encoded `127.0.0.1`
Fixed in QR generation behavior.

QR generation now honors `HONEYCHAIN_BASE_URL` when configured. Otherwise generated QR responses use the active request host, so deployed instances can produce QR codes for the reachable deployment URL rather than a hard-coded loopback address.

For deployment, set:

```powershell
$env:HONEYCHAIN_BASE_URL="https://YOUR-DEPLOYED-DOMAIN"
```

before regenerating demo data / QR assets.

## UI fixes

### UI-01 — truncated “Run demo harvest for …” action
Fixed with a responsive non-truncating action layout and full-width mobile behavior.

### UI-02 — integrity verification tick contrast
Made the verification indicator explicitly high-contrast.

### UI-03 — “Evidence score” ambiguity
The consumer page now labels the numeric indicator as **Evidence completeness**. Cryptographic integrity remains separately represented by the verification banner.

### UI-04 — persistent registration confirmation
Registration success/failure is now shown as a temporary toast notification instead of a permanent dashboard panel.

### UI-05 — stale registered-hive/action state after demo reset
Demo reset now clears preferred demo-hive state, hides the post-registration action panel, and rebuilds the selector from the clean database.

### UI-06 — old event-log history after demo reset
Demo reset now clears the in-page event log before recording the new reset event.

### UI-07 — second-click action failures
Key batch actions lock immediately while a request is in progress, preventing accidental duplicate submissions and misleading second-click errors.

### UI-08 — alert refresh gives no feedback
Alert refresh now shows a visible loading/updated result in the event log and locks the action while the request is running.

## Release validation performed in the build environment

- Python syntax compilation: PASS
- JavaScript syntax check with Node: PASS
- Dependency-free UI contract test: PASS
- SQLite seed/reset/idempotent demo-harvest runtime check using isolated dependency stubs: PASS
- Clean bundled database verified: 3 hives, 2 committed batches, 1 manual-review batch
- Bundled QR/evidence files restored as real PNG assets

## Environment limitation
The build environment used for packaging does not have Flask and the required runtime dependencies installed, and external package installation is unavailable. Therefore a fresh full Flask/browser regression could not be rerun inside this packaging environment after the final repair pass.

The browser acceptance results from the user's Windows environment were the source of the confirmed regressions, and the repaired code paths were additionally exercised through dependency-isolated SQLite runtime checks.

## Deployment note
Do not treat the local SQLite hash-chain as a production blockchain. For production deployment, use authenticated identities, proper secret management, a persistent production database, calibrated real-field AI models, observability/security controls, and a permissioned multi-organization ledger where required.
