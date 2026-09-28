# Nectar Chain — Final Regression Audit v2.7.7

## Scope
This release is the repair candidate produced after the independent v2.7.6 audit. The v2.7.6 blockers were repaired in v2.7.7 before packaging.

## Verified in the build environment

- Python syntax compilation: PASS
- JavaScript syntax check with Node: PASS
- Dependency-free UI contract checks: PASS
- Clean bundled SQLite database: 3 hives, 3 batches, 2 committed + 1 manual-review
- SQLite foreign-key check: PASS
- SQLite WAL mode retained: PASS
- Bundled QR and evidence assets are real PNG files: PASS
- Reset/seed logic exercised with isolated dependency stubs: PASS
- Concurrent reset helper exercise: PASS

## Repairs in v2.7.7

1. **Reload demo data button** is now wired to `/api/demo/seed`.
2. Demo reset clears browser state: event log, verification cache, preferred hive, registration form and post-registration action panel.
3. Demo reset clears SQLite rows in-place instead of deleting/recreating the database file. This removes the Windows file-lock race discovered during the earlier `/api/hives` HTTP 500 failure.
4. The reset helper serializes filesystem cleanup as an additional safeguard.
5. `/qr/<batch_id>` uses the same deployment base URL resolver as commit-time QR generation.
6. Demo-only destructive controls respect `NECTAR_DEMO_MODE`.
7. Newly registered-hive quick-action text is responsive and no longer relies on a fixed-width truncated button.
8. Static asset cache-busting is aligned to v2.7.7.

## Browser limitation
The packaging environment does not contain Flask and its runtime dependencies, so a fresh real-browser regression of v2.7.7 could not be executed inside this environment. The user's Windows environment is therefore still the authoritative final smoke-test environment.

## Required final smoke test before public deployment

```powershell
python -m pip install -r requirements.txt
python seed_demo.py --reset
python self_test.py
python app.py
```

Then verify in the browser:

- Reload demo data button works and clears old event history/state.
- Register a hive and confirm the full Hive ID is visible in the quick action.
- Run demo harvest twice rapidly; only one batch is created.
- Validate/commit double-click protection works.
- Verify full chain.
- Open a committed consumer page.
- Deploy with `HONEYCHAIN_BASE_URL` set and regenerate demo data so QR assets target the deployment URL.
- Scan the deployed QR from a phone.
