# Bugfix Report — v2.7.9

## Fixed: persistent post-registration harvest panel

### Observed behavior
After registering a hive, the registration success toast disappeared after a few seconds, but a separate persistent “Ready to create a harvest batch” box remained below the registration form. This duplicated functionality already available in the Harvest events section and made the UI look stale.

### Root cause
The dashboard rendered a separate `registration-demo-action` panel after every successful registration and the JavaScript contained a dedicated `run-new-hive-demo` quick-action. The Harvest events section already provides the canonical demo-harvest selector and action.

### Fix
- Removed the `registration-demo-action` block from `templates/dashboard.html`.
- Removed `showNewHiveDemoAction()` and its event handler from `static/js/app.js`.
- Removed quick-action wiring from `runDemoHarvestForSelectedHive()`.
- Kept `state.preferredDemoHiveId` so the newly registered hive is automatically selected in the existing Harvest events selector.
- Kept the temporary registration success toast as the sole post-registration confirmation.
- Removed obsolete CSS for the deleted panel.
- Updated UI contract/self-test checks to ensure the removed panel cannot regress.

### Expected final flow
Register hive → temporary “Registration verified” toast → new hive selected in Harvest events → user clicks “Run demo harvest” there.
