# Nectar Chain v2.7.2 — Final Regression Hardening

## Findings carried forward from the test pass

1. Manual refresh previously appeared silent / could overlap. The current UI already uses explicit manual refresh state and no timer-based refresh.
2. Registration accepted poor test values in earlier iterations. Frontend and backend validation are retained, with Unicode-safe browser validation for real names/locations.
3. Repeated demo-harvest requests are guarded in the UI and backend depletion is returned as controlled HTTP 409 rather than an unhandled 500.
4. Tampering detection, chain verification, consumer verification, reset/reload and rejection flows were exercised successfully during the browser pass.

## New hardening in v2.7.2

- Evidence bundles now fail integrity checks when a linked file is missing or modified.
- Rejected batches can no longer be modified through evidence upload, image analysis or health-screen actions.
- Uploaded images are validated as readable images before being stored as evidence.
- Custody verification validates stage order and current-stage consistency.
- Custody stage changes are sequential only.
- Frontend registration accepts Unicode letters/numbers in beekeeper, apiary, region and floral-source text.
- Release/version cache strings are aligned to v2.7.2.

## Honest prototype scope

- Trust layer: local SQLite SHA-256 hash chain, not a decentralized blockchain.
- IoT/camera data in the bundled demo: synthetic.
- AI: baseline/demo screening and yield model, not production-validated disease diagnosis or accuracy.
