# Nectar Chain — SIH 26021 Working Prototype v2.7.9

Nectar Chain implements an **evidence-backed honey traceability and smart beekeeping workflow** for SIH 26021.

## Core differentiator

> **We don't put claims on the chain — we put evidence on it.**

The prototype follows:

```text
Hive sensors
    ↓
Weight-drop harvest detection
    ↓
Context + camera evidence
    ↓
AI-assisted validation
 ┌───────────────┐
 │ APPROVE?      │
 └──────┬────────┘
   YES  │   NO
    ↓   │    ↓
Evidence gate
    ↓
Hash-chain   Human / lab review
commit       (no QR until approved)
    ↓
QR generated
    ↓
Consumer scans
    ↓
Recompute record + evidence + chain + custody hashes
    ↓
VERIFIED / TAMPERING DETECTED
```

## Upgraded prototype capabilities

### 1. Automatic harvest-event detection
- Load-cell/weight data is the primary harvest trigger.
- A significant weight drop creates a candidate harvest event.
- The default **1.5 kg threshold is configurable** via `HARVEST_DROP_KG` and is a prototype/demo value; real deployment would calibrate it using actual hive data and sensor noise.

### 2. Multi-sensor AI-assisted validation
- Temperature + humidity provide environmental context.
- Weight trend provides the primary harvest/productivity signal.
- A baseline scikit-learn regression predicts expected yield from synthetic demonstration data.
- Harvest quantity is checked against predicted yield for anomalies.
- Hive-health risk is a **screening signal**, not a definitive disease diagnosis.

### 3. Camera evidence bundle
A harvest can include:
- **Pre-harvest image**
- **Post-harvest image**
- Optional **hive-health screen**

Images remain off-chain. Their SHA-256 digests are included in the evidence bundle hash linked to the committed record.

The bundled demo generates clearly labelled **synthetic camera images** so the evidence workflow can be demonstrated without physical camera hardware.

### 4. Early hive-health warning
- Environmental/weight patterns produce LOW/MEDIUM/HIGH prototype health-risk signals.
- Optional visual screening provides a **Varroa-associated visual risk signal** using the bundled heuristic or an optional trained CNN.
- Medium/high signals create dashboard alerts for beekeeper inspection.
- These are **screening/decision-support signals**, not veterinary diagnoses.

### 5. Verify-then-Commit
- A candidate harvest is created from the weight-change trigger.
- Pre/post harvest evidence is required before trusted commitment.
- The AI decision gate combines sensor trends, visual evidence and hive-health context.
- Suspicious candidates enter `PENDING_REVIEW`; reviewers can approve or reject.
- Only approved, evidence-complete batches receive a record hash and QR.

### 6. Tamper-evident trust layer
The prototype uses a **local SQLite hash-chain**, not a decentralized blockchain network.

A committed batch binds:
- batch metadata
- observed harvest delta
- AI validation result
- environmental context
- visual screening result
- evidence bundle hash
- previous batch hash
- commit timestamp

Verification recomputes:
1. the record hash,
2. the evidence bundle hash,
3. the batch chain,
4. the custody chain.

A mismatch is surfaced as tampering.

### 7. Consumer verification
The QR encodes the verification page. The consumer can inspect:
- beekeeper and hive
- region and floral source
- harvest date and quantity
- environmental context
- predicted yield
- hive-health risk signal
- evidence images
- custody timeline
- cryptographic hashes

## Storage model

### Off-chain SQLite
Stores detailed sensor logs, metadata, AI outputs, image files and custody history.

### Trust layer
Stores only the compact cryptographic representation needed to make later modifications detectable.

### Production scale-up
The local hash-chain can be replaced by a permissioned multi-organization ledger such as Hyperledger Fabric when KVIC/institutional participants need shared governance and write access.

## Run in VS Code / Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed_demo.py --reset
python app.py
```

Open:

`http://127.0.0.1:5000`

For a LAN or hosted demo QR, set `HONEYCHAIN_BASE_URL` before starting the server so generated QR codes point to the reachable address.

In another terminal:

```powershell
.\venv\Scripts\Activate.ps1
cd iot_simulator
python simulate.py
```

## Demo records

All bundled records and images are **synthetic demonstration data**.

- **HC-0001** — low-risk, approved, committed, camera evidence, QR ready
- **HC-0002** — medium-risk, visual/quantity warning, held for manual review, no QR until approved
- **HC-0003** — second approved batch, forming a visible hash-chain link

## Main endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/hives` | Registered hives + current health summary |
| POST | `/api/hives` | Register hive |
| POST | `/iot/reading` | IoT ingestion + harvest detection |
| GET | `/api/batches` | List candidate/committed batches |
| GET | `/api/batch/<id>` | Full batch record |
| POST | `/api/batch/<id>/validate` | Re-run evidence + AI decision gate and commit if approved |
| POST | `/api/batch/<id>/manual-approve` | Human-in-the-loop approval |
| POST | `/api/batch/<id>/manual-reject` | Human-in-the-loop rejection; no ledger/QR |
| POST | `/api/batch/<id>/stage` | Advance custody stage |
| GET | `/api/verify/<id>` | Verify record, evidence, batch-chain and custody integrity |
| POST | `/api/batch/<id>/tamper` | Demo-only off-chain tamper |
| POST | `/api/batch/<id>/evidence` | Upload pre/post/health camera evidence before commit |
| POST | `/api/batch/<id>/analyze-image` | Supplementary visual health screening |
| POST | `/api/batch/<id>/demo-health-screen` | Generate/demo a visual health screen |
| GET | `/api/health-alerts` | Early-warning alerts |
| GET | `/api/summary` | Dashboard/system counters and chain status |
| GET | `/api/hive/<id>/health` | Hive-health summary and alerts |
| GET | `/qr/<id>` | Batch QR |
| GET | `/scan/<id>` | Consumer verification page |
| POST | `/api/demo/seed` | Reload deterministic synthetic data |
| POST | `/api/demo/harvest` | Trigger harvest through the same ingestion route |

## Prototype completion target

**Demo-grade working prototype: ~92% complete.** The core workflow is implemented end-to-end: IoT ingestion/simulation, weight-triggered harvest detection, pre/post evidence capture and hashing, baseline AI-assisted validation, human review/rejection, tamper-evident hash-chain commitment, custody hashing, QR generation, consumer verification and tamper demonstration.

**Production-scale final system: ~55% complete.** Remaining work includes physical ESP32/sensor deployment, calibrated real-field AI models and datasets, authenticated institutional identities, production security/observability and a live permissioned blockchain network.

## Presentation-safe claims

Use:
- “sensor-backed evidence”
- “AI-assisted hive-health risk screening”
- “Varroa-associated visual risk signal”
- “tamper-evident hash-chain prototype”
- “supports provenance verification”

Do not say:
- sensor data proves honey purity
- the DHT22 diagnoses disease
- the current prototype is a decentralized blockchain
- AI provides a veterinary diagnosis
- the prototype guarantees regulatory compliance

Laboratory testing remains complementary for real disease confirmation and chemical honey-authenticity testing.


## v2.2.0 Regression hardening

- Hive registration now updates the dashboard immediately and remains visible even when another dashboard API has a transient failure.
- Dashboard data sources refresh independently instead of one failed request blanking all sections.
- Legacy database migrations now cover hive, reading, AI, evidence and alert fields used by the current UI.
- Repeated **Run demo harvest** clicks now fail safely with an actionable 409 once the synthetic hive is depleted instead of an HTTP 500.
- Registration validates/strips input and rejects duplicate/overlong hive IDs cleanly.
- Register/demo buttons are disabled during requests to prevent accidental duplicate submissions.

## v2.1.1 UI / responsive hardening

- Consumer verification page no longer inherits the dashboard two-column grid.
- Desktop consumer layout now uses the full available content width with stable two-column batch/QR presentation.
- Evidence and camera cards use consistent responsive grids.
- Dashboard panels, hashes, buttons and long metadata wrap safely at narrower widths.
- Mobile breakpoints were tightened for phones and tablets while preserving the desktop presentation.


## v2.2.4 refresh reliability fix
Manual dashboard refresh now has explicit UI feedback, safe error handling, and no automatic refresh timer. See `BUGFIX_REPORT_v2.2.4.md`.



## v2.7.9 final UI refinement

This release incorporates the regression findings from the full prototype test pass and hardens evidence/custody integrity.

- Manual dashboard refresh remains user-triggered only; no timer-based refresh loop was reintroduced.
- Hive registration validation remains enforced on both frontend and backend, with Unicode-safe text-field validation in the browser.
- Rejected batches are immutable: evidence upload, image analysis, health-screen actions and manual re-decisions are blocked.
- Evidence integrity now detects missing or modified evidence files; a committed batch cannot verify if required evidence is missing or altered.
- Custody verification now checks that stage hashes progress in order and that the batch's current stage matches the hashed custody trail.
- Custody advancement is sequential: Harvested -> Processing -> Distribution -> Retail.
- Uploaded camera files are validated as readable images before they are accepted as evidence.
- CSS cache-busting is aligned to the release version.

## v2.2.5 validation hardening
- Registration now rejects whitespace-only and punctuation-only values.
- Hive IDs must match a safe 3–64 character format: letters/numbers with `-`/`_`.
- Added regression coverage for invalid registration values.
