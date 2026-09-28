# Nectar Chain — Deployment Preparation v2.7.9

## Final local smoke test on Windows

```powershell
python -m pip install -r requirements.txt
python seed_demo.py --reset
python self_test.py
python app.py
```

Open `http://127.0.0.1:5000` and confirm the clean seeded dashboard.

## Demo reset

The **Reload demo data** button is fully wired in v2.7.9. It resets the demo database in-place (without deleting the SQLite file), clears stale browser state/event history, and reloads the deterministic demo data.

## QR / deployment URL

Set the reachable deployment URL before generating demo QR assets:

```powershell
$env:HONEYCHAIN_BASE_URL="https://your-domain.example"
python seed_demo.py --reset
python app.py
```

All generated QR assets and the `/qr/<batch_id>` endpoint use this configured base URL.

For a same-LAN demonstration, use the laptop's LAN address instead, for example:

```powershell
$env:HONEYCHAIN_BASE_URL="http://10.20.65.120:5000"
```

The phone and laptop must be on the same network and Windows Firewall must allow the Flask port.

## Demo controls

Demo-only destructive controls (demo reset, synthetic harvest, tamper simulation, demo health screen) are enabled by default for the hackathon prototype. To disable them on a public non-demo instance:

```powershell
$env:NECTAR_DEMO_MODE="0"
```

Then restart the server. The consumer scan/verification routes and normal read-only APIs remain available.

## Production hardening

This remains a demo-grade prototype. A production deployment should still add:

- production WSGI server and reverse proxy
- HTTPS
- authenticated institutional identities / RBAC
- secret management
- production database and backups
- structured logging and monitoring
- calibrated IoT thresholds and sensor authentication
- real labeled AI datasets and validation
- permissioned multi-organization blockchain/ledger if required
