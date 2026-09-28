# Bugfix Report — v2.7.8

## Test-harness correction
The application intentionally returns HTTP 200 with `harvest_event.idempotent=true` when a rapid repeated demo-harvest request is deduplicated. The previous regression harness only accepted 201/409 and therefore falsely marked the healthy idempotent response as a failure. The harness now accepts 200 and checks the idempotent flag. No production application behavior was changed.
