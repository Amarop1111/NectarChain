# Nectar Chain v2.2.0 — Functional / Regression Audit

## v2.2.0 fixes confirmed

- Registration dashboard resilience: PASS
- Legacy SQLite schema migration hardening: PASS
- Repeated demo-harvest HTTP 500 regression: PASS
- Per-record list API resilience: PASS

## Verified locally

- Python source compilation: **PASS**
- JavaScript syntax check: **PASS**
- Deterministic demo seed: **PASS**
- Seeded chain verification: **PASS**
- Evidence bundle hash integrity: **PASS**
- Record hash tamper detection: **PASS**
- Evidence-file tamper detection primitive: **PASS**
- Manual approval of a previously pending batch appends safely to the chain: **PASS**
- Manual rejection produces no record hash and no QR: **PASS**
- Non-demo IoT harvest candidates are blocked from auto-commit until evidence is complete: **PASS**
- Demo IoT harvest path collects synthetic evidence and can complete the full pipeline: **PASS**
- Re-validation of suspicious batches remains in manual review: **PASS**
- Rejected batches cannot be revalidated in-place: **PASS**

## Browser/server limitation in the audit environment

The execution environment used for this review does not have Flask installed, and outbound package installation was unavailable. Therefore a live Flask server/browser session could not be launched here. The project was still statically compiled, JavaScript-checked, and its core database/hash/evidence/IOT processing functions were exercised with a lightweight Flask compatibility harness.

The repository includes `self_test.py`, which should be run on the target Windows machine after `pip install -r requirements.txt`; it uses Flask's real test client and covers the HTTP endpoints and browser-facing workflow without requiring an external network.
