# Nectar Chain prototype — upgrade notes

This version updates the prototype to match the architecture agreed for SIH 26021.

## Main upgrades

### Harvest evidence
- Weight remains the primary harvest-event trigger.
- Pre- and post-harvest camera evidence can be uploaded before commitment.
- Demo mode automatically creates clearly labelled synthetic pre/post images.
- Each evidence file receives a SHA-256 digest.
- The evidence bundle digest is bound into the committed record.

### AI / smart beekeeping
- Temperature + humidity + weight trends provide environmental/colony context.
- Yield prediction remains a synthetic-data baseline for the prototype.
- Hive-health risk is LOW/MEDIUM/HIGH screening rather than a diagnosis.
- Optional visual screening provides a Varroa-associated risk signal.
- Medium/high warning signals appear in the dashboard and health-alert feed.

### Verify-then-Commit
- Candidate harvests are validated before commitment.
- Suspicious candidates stay in manual review and receive no QR until approval.
- Manual approval commits the current evidence bundle and updates the hash-chain correctly even when an earlier batch was approved later.

### Verification
The verification endpoint now checks:
1. record hash,
2. evidence bundle hash,
3. batch hash-chain,
4. custody-event chain.

A changed evidence file is now detectable as an evidence-bundle mismatch.

### UI
- Verification results appear directly on the batch card.
- Camera evidence thumbnails are visible in the dashboard and consumer page.
- Hive health-risk badges and early-warning alerts were added.
- Consumer page shows the linked evidence and cryptographic evidence hashes.

## Important prototype honesty
- The current trust layer is a local SQLite hash-chain, not a decentralized blockchain network.
- The disease feature is an AI-assisted screening signal, not a veterinary diagnosis.
- The bundled camera images are synthetic demonstration evidence, not real hive photographs.
- Real deployment would use calibrated field thresholds, real labelled datasets, authenticated institutional identities and a permissioned multi-organization ledger.


## v2.1.0 hardening
- Ledger commitment now requires complete pre/post-harvest evidence.
- Added an explicit re-validation decision gate after evidence upload.
- Added manual reject path with no hash and no QR.
- Added stable commit sequence to prevent out-of-order manual approvals from breaking the chain.
- Fixed committed-batch immutability for demo health-screen actions.
- IoT processing is centralized in `process_iot_reading()` so demo and simulator exercise the same core path.
- Added `/api/summary` for accurate dashboard counters.
- Simulator marks harvest-triggered readings as demo mode so the evidence/AI/commit pipeline can be demonstrated end-to-end.
