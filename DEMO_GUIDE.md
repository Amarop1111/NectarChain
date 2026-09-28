# Nectar Chain — Internal Hackathon / SIH 26021 Demo Guide

## What the upgraded prototype demonstrates

**Weight trigger → multi-sensor context + camera evidence → AI-assisted validation → approve/review → hash-chain commit → QR → consumer verification**

The prototype trust layer is a local cryptographically linked SQLite hash-chain. It is a prototype representation of the blockchain layer; production scale-up can move the commit layer to a permissioned multi-organization blockchain.

## Fastest setup

```powershell
python -m pip install -r requirements.txt
python seed_demo.py --reset
python app.py
```

Open:

`http://127.0.0.1:5000`

Optional simulator in another terminal:

```powershell
cd iot_simulator
python simulate.py
```

## Recommended 3-minute judge demo

### 1. Start at the dashboard
Point out:
- registered hives
- committed batches
- IoT readings
- manual review count
- active health warnings
- chain integrity

Say:

> “The weight sensor is the harvest trigger. Temperature and humidity provide context, camera evidence can corroborate the event, and AI validates the event before the record can be committed.”

### 2. Show the hive-health layer
Open the Hive monitoring section.

For HIVE-002, the dashboard contains a **MEDIUM** health-risk signal.
Explain:

> “Environmental and weight trends are used for early-risk screening. A visual screen can provide an additional Varroa-associated signal. The output is an early warning for inspection, not a disease diagnosis.”

### 3. Show HC-0002 — human-in-the-loop
Open the ledger card.

It should show:
- `MANUAL REVIEW`
- medium risk
- yield inconsistency
- visual screening evidence
- complete pre/post evidence
- no committed hash
- no QR yet

Explain:

> “AI does not get unrestricted authority to write trusted records. Suspicious evidence is held for review.”

Optionally click **Run demo health screen** to demonstrate the image-analysis path.

Then click **Manual approve**. The system commits only after the evidence-complete gate passes.

Now the batch receives:
- committed hash
- QR
- custody event

### 4. Show HC-0001 — evidence-backed approved batch
Open HC-0001.

Show:
- 35.6 kg → 28.2 kg
- 7.4 kg harvest delta
- predicted yield 7.7 kg
- low hive-health risk
- pre-harvest image
- post-harvest image
- health-screen image

Explain:

> “The images are linked to the same batch as the sensor evidence. Their SHA-256 digests are part of the evidence bundle hash.”

### 5. Verify the committed batch
Click **Verify hash**.

The card should visibly display:

**✓ HASH VERIFIED**

with:
- record hash valid
- evidence bundle valid
- batch chain valid
- custody trail valid

### 6. Prove tamper detection
Click **Simulate tampering** on HC-0001.

Then click **Verify hash** again.

The result should become:

**⚠ TAMPERING DETECTED**

Explain:

> “We changed a database value without changing the committed hash. Verification recomputed the record and exposed the mismatch.”

You can also demonstrate the evidence side by replacing an evidence file in a controlled local test: the evidence bundle hash will no longer match the committed evidence digest.

### 7. Show the consumer side
Click **Open consumer page** for HC-0001.

Show:
- Verified evidence status
- QR
- origin / beekeeper / hive
- harvest details
- environmental context
- predicted yield
- risk status
- pre/post images
- evidence hashes
- custody trail

Say:

> “The QR doesn't contain the data. It points to the verification page, where the backend recomputes the committed evidence and chain relationships.”

### 8. Close with full chain verification
Click **Verify full chain**.

Finish with:

> “So our key difference is not simply putting honey records on a blockchain. We first create machine-backed evidence, validate it, and only then make the evidence-backed record tamper-evident and consumer-verifiable.”

## What the camera evidence means

### Pre/post harvest images
Used as visual corroboration of the extraction event. They do not establish the exact kilograms harvested by themselves; the load-cell measurement remains the primary physical trigger.

### Health-screen image
Used as a supplementary visual screening signal. The prototype targets a **Varroa-associated visual risk signal**. A real deployment would require a properly labelled, field-validated dataset and expert/lab confirmation.

## Sample synthetic records

### HC-0001 — approved
- HIVE-001 / Ramesh Kumar / Nilgiris
- 35.6 kg → 28.2 kg
- 7.4 kg harvest delta
- 34.47 °C / 53.77% RH context
- predicted yield 7.7 kg
- low hive-health risk
- complete synthetic camera evidence
- committed + QR

### HC-0002 — manual review
- HIVE-002 / Meena Devi / Kanyakumari
- 29.0 kg → 23.6 kg
- 5.4 kg harvest delta
- 37.83 °C / 68.10% RH context
- predicted yield 8.7 kg
- medium risk
- quantity mismatch + visual screening warning
- held before commit

### HC-0003 — second chain link
- HIVE-003 / Arun Raj / Idukki
- 33.2 kg → 26.4 kg
- 6.8 kg harvest delta
- predicted yield 6.9 kg
- low risk
- committed after HC-0001, so its previous hash visibly links back to HC-0001

All records/images above are synthetic demonstration data.

## New v2.1.0 decision-gate demo

For a clean end-to-end candidate path, select the desired hive under **Demo hive**, then click **Run demo harvest**. The demo creates the weight-trigger event, generates synthetic pre/post camera evidence, reruns AI validation, and commits only if the evidence gate passes.

For a suspicious candidate, use **Validate & commit**, **Manual approve**, or **Reject**. A rejection never receives a ledger hash or QR.

The **Add camera evidence** flow accepts pre-harvest, post-harvest and optional health-screen images. After upload, click **Validate & commit** to rerun the evidence + AI decision gate.
