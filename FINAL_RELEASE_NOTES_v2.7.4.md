# Nectar Chain v2.7.4 — Registration Integrity Hardening

## Findings carried forward from the test pass

1. Manual refresh previously appeared silent / could overlap. The current UI already uses explicit manual refresh state and no timer-based refresh.
2. Registration accepted poor test values in earlier iterations. Frontend and backend validation are retained, with Unicode-safe browser validation for real names/locations.
3. Repeated demo-harvest requests are guarded in the UI and backend depletion is returned as controlled HTTP 409 rather than an unhandled 500.
4. Tampering detection, chain verification, consumer verification, reset/reload and rejection flows were exercised successfully during the browser pass.

## Carried-forward hardening

- Evidence bundles now fail integrity checks when a linked file is missing or modified.
- Rejected batches can no longer be modified through evidence upload, image analysis or health-screen actions.
- Uploaded images are validated as readable images before being stored as evidence.
- Custody verification validates stage order and current-stage consistency.
- Custody stage changes are sequential only.
- Frontend registration accepts Unicode letters/numbers in beekeeper, apiary, region and floral-source text.
- Release/version cache strings are aligned to v2.7.4.

## Honest prototype scope

- Trust layer: local SQLite SHA-256 hash chain, not a decentralized blockchain.
- IoT/camera data in the bundled demo: synthetic.
- AI: baseline/demo screening and yield model, not production-validated disease diagnosis or accuracy.


## v2.7.4 registration fix

- Hive IDs are canonicalized to uppercase and validated case-insensitively for uniqueness.
- Registration uses a semantic HTML form with explicit field names and autocomplete disabled.
- The server verifies the database round-trip after insertion and refuses to report success if persisted values differ from the submitted canonical payload.
- The browser verifies the persisted hive by reading it back from the authoritative `/api/hives` endpoint before updating the dashboard; it no longer depends on optional response metadata.
- Registration success now records the exact saved hive metadata in the event log and a visible confirmation panel.
- Frontend asset URLs are cache-busted with the release version to prevent stale JavaScript/CSS from surviving an upgrade.
- Added `/api/version` mismatch detection so an old backend cannot silently masquerade as the current release.
- Demo harvest now supports any registered hive; a new hive receives a synthetic baseline reading before its demo harvest event, so its batch can appear in the ledger after verification/commit.


See REGISTRATION_INTEGRITY_FIX_v2.7.4.md for the registration and selected-hive demo-harvest fixes.
