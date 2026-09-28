# Nectar Chain v2.2.0 — Regression Audit

## Static checks

- Python source compilation: PASS
- JavaScript syntax check (`node --check`): PASS

## Core workflow checks exercised without a live Flask dependency

- Fresh deterministic seed: PASS
- `/api/hives` equivalent route logic: PASS
- `/api/batches` equivalent route logic: PASS
- `/api/summary` equivalent route logic: PASS
- Hive registration with trimmed values: PASS
- Duplicate hive rejection: PASS
- Missing registration fields rejection: PASS
- Newly registered hive appears in the hive list: PASS
- IoT reading ingestion and candidate harvest creation: PASS
- Demo harvest + evidence + commit path: PASS
- Repeated demo harvest eventually returns controlled HTTP 409 instead of an uncaught 500: PASS
- Legacy SQLite schema migration for newly required columns: PASS

## Environment limitation

The current execution container does not have Flask installed and external package installation is unavailable. Therefore the real Flask test-client/browser regression suite (`self_test.py`) could not be executed here. The source was still compiled and the backend functions were exercised with a lightweight Flask compatibility harness.

On the target Windows environment, install `requirements.txt`, reset the demo database, start the Flask app, and perform the full browser regression pass from a clean extraction.
