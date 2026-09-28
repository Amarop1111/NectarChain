# Nectar Chain — Final Release Notes v2.7.5

## Fix: Registered hive → demo harvest → batch ledger path

The previous release correctly registered new hives but did not make the next demo-harvest action explicit enough. The dashboard could keep the previous Demo hive selection, causing an operator to run a harvest for the wrong hive or assume registration itself should create a batch.

### Changes

- Newly registered hive is automatically selected in **Demo hive**.
- Registration success now includes an explicit **Run demo harvest for <HIVE-ID>** action.
- The UI explicitly distinguishes hive registration from harvest-event creation.
- The demo-harvest result refreshes the `/api/batches` source and takes the operator to the Batch Ledger.
- Pending-review demo harvests are still visible in the ledger; commitment remains a separate Verify-then-Commit step.
- The existing backend demo-harvest path creates a synthetic sensor baseline for a newly registered hive, applies a deterministic weight drop, generates synthetic evidence, and passes the event through the normal decision gate.
- Added a static regression contract for the registered-hive → demo-harvest → ledger path.

## Important demo behavior

A registered hive is **not** itself a harvest batch. Registration creates the monitoring identity. A batch is created when a weight-triggered harvest event occurs. In the prototype, **Run demo harvest** simulates that event for the selected hive.
