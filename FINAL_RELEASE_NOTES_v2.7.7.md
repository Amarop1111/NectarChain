# Nectar Chain — Final Release Notes v2.7.7

## Purpose
Post-audit repair release following the detailed v2.7.6 independent verification.

## Repaired blockers

### 1. Reload demo data button was not wired
The dashboard `Reload demo data` button now performs the real `/api/demo/seed` reset path, clears stale client state, clears the in-page event log, reloads the deterministic dataset, and reports the result.

### 2. Demo reset no longer deletes the live SQLite file
The reset path now clears rows in a serialized transaction while keeping the SQLite database file and WAL configuration intact. This avoids the Windows file-lock race that caused `database is locked` / `/api/hives` 500 failures during reset + refresh activity.

### 3. QR URL handling unified
The `/qr/<batch_id>` route now uses the same `HONEYCHAIN_BASE_URL` / request-host-aware resolver as commit-time QR generation.

### 4. Reset stale-state cleanup made real
Demo reset clears hives, batches, alerts, summaries, verification state, selected demo hive state, registration UI and event-log history before rebuilding the dashboard.

### 5. Demo-only endpoint guard
Demo reset, demo harvest, tamper simulation and demo health-screen endpoints now respect `NECTAR_DEMO_MODE`. The hackathon build defaults this to enabled; set it to `0` on a non-demo public instance.

## Retained hardening

- rapid repeated demo harvests are idempotent
- repeated validation actions are locked at the UI layer
- registration is canonicalized and verified against persisted data
- evidence files are validated and hashed
- rejected batches are immutable
- custody transitions are sequential and re-verifiable
- verification distinguishes record, evidence, chain and custody integrity
- dashboard refresh is manual only

## Validation

The release package includes updated smoke/regression and UI-contract coverage for the reset button, reset-state cleanup and demo-control guard.

The local browser regression on the user's Windows environment should still be run once against this exact v2.7.7 package before the first public deployment.
