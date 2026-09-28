# Nectar Chain — Prototype Completion Matrix

## v2.2.0 regression hardening

The latest regression pass fixed dashboard resilience, legacy-schema migration gaps, hive-registration UX/error handling, and the repeated-demo-harvest HTTP 500 path.

## What “completion” means here

The percentage below measures completion against the **demo-grade main working prototype** represented by the current SIH architecture: simulated/real IoT ingestion, evidence capture, AI-assisted validation, human review, tamper-evident commitment, custody, QR verification and tamper demonstration.

It does **not** count production-only items such as a live Hyperledger network, physical hive deployment across apiaries, or field-trained AI validation datasets.

## Demo-grade prototype: ~92% complete

| Capability | Status | Notes |
|---|---:|---|
| Hive registry + monitoring dashboard | 100% | Hive registration, latest readings and health summary |
| IoT ingestion / simulator | 100% | `/iot/reading` + simulator exercise the same processing path |
| Weight-based harvest detection | 100% | Configurable threshold; candidate event creation |
| Pre/post harvest evidence | 100% | Upload + synthetic demo capture; SHA-256 file hashes |
| Evidence bundle hashing | 100% | Bundle digest bound to committed record |
| Harvest validation | 95% | Baseline model/rules; field calibration remains |
| Yield prediction | 90% | Synthetic-data regression baseline; real-data training remains |
| Hive-health risk screening | 90% | Sensor screening + optional visual signal; not diagnosis |
| Verify-then-Commit gate | 100% | Evidence + AI decision before commit |
| Human review + reject path | 100% | Approve or reject; rejected batches get no QR |
| Tamper-evident hash chain | 100% | Stable commit sequence + SHA-256 record links |
| Custody/event chain | 100% | Stage hashes linked to committed record |
| QR generation + consumer page | 100% | Origin, evidence, custody and integrity checks |
| Tamper demonstration | 100% | Record and evidence tamper detection |
| Automated smoke/regression test | 100% | `self_test.py` included for local validation |
| **Overall demo-grade target** | **~92%** | Remaining gap is refinement/polish, not a missing core workflow |

## Production-scale system: ~55% complete

The remaining work includes:

- physical ESP32 + load-cell + environmental sensors + camera deployment
- calibrated real-field datasets for harvest, yield and hive-health models
- model evaluation on unseen hives/apiaries
- authenticated institutional identities and role-based access control
- permissioned multi-organization blockchain deployment (e.g. Hyperledger Fabric)
- production observability, security hardening, key management and operational support

## Recommended PPT wording

For the Technical Approach slide, use:

> **Prototype Status: ~92% of the demo-grade working system implemented**

For a more conservative slide claim:

> **Core Prototype: ~90% complete**


## v2.2.5 validation hardening
- Registration now rejects whitespace-only and punctuation-only values.
- Hive IDs must match a safe 3–64 character format: letters/numbers with `-`/`_`.
- Added regression coverage for invalid registration values.
