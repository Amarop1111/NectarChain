# Registration Integrity Fix — v2.7.4

## Problem fixed
A newly registered hive could appear on the dashboard with values that did not match what the operator believed had been entered. The registration path did not explicitly prove that the exact submitted payload survived the browser → API → SQLite round trip.

## Fix
- Registration is now a real semantic form with explicit field names and autocomplete disabled.
- Hive IDs are canonicalized to uppercase before persistence.
- Hive IDs are unique case-insensitively (`HIVE-004` and `hive-004` are treated as the same ID).
- Text fields are whitespace-normalized before persistence.
- Backend checks for an existing normalized Hive ID before insert.
- Backend reads the newly stored row back and compares all five registration fields against the canonical request. A mismatch is rejected and removed rather than reported as success.
- Frontend compares the API response field-by-field with the exact payload it submitted before rendering the hive as registered.
- Successful registration displays the exact saved metadata in the event log and a registration-status panel.
- Static JS/CSS assets use v2.7.4 cache-busting query strings so an upgraded prototype does not silently run an older cached client.

## Validation performed
- Python syntax compilation: PASS.
- Browser JavaScript syntax check (`node --check`): PASS.
- Bundled demo SQLite data contains the expected three seeded hives.
- Normalized unique-index creation was tested successfully against the bundled database.
- `self_test.py` was expanded to verify exact registration payload round-trip, case-insensitive duplicates, and whitespace/case canonicalization.

The full Flask/browser runtime test was not executed in this container because Flask is not installed here; run `python self_test.py` on the target Windows environment after `pip install -r requirements.txt`.
