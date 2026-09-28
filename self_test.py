"""Nectar Chain end-to-end prototype smoke/regression test.

Run after installing requirements:
    python self_test.py

This intentionally uses Flask's test client, so no browser or external network is required.
All generated data is synthetic and the test resets the local demo database.
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from app import DB_PATH, app
import seed_demo

ROOT = Path(__file__).resolve().parent


def assert_status(resp, expected: int, label: str) -> None:
    assert resp.status_code == expected, f"{label}: expected {expected}, got {resp.status_code}: {resp.get_data(as_text=True)[:300]}"


def main() -> None:
    seed_demo.reset_db()
    seed_demo.seed()

    with app.test_client() as client:
        # Baseline pages/APIs
        assert_status(client.get("/"), 200, "dashboard")
        assert_status(client.get("/api/hives"), 200, "hives")
        assert_status(client.get("/api/batches"), 200, "batches")
        assert_status(client.get("/api/summary"), 200, "summary")
        assert_status(client.get("/api/health-alerts"), 200, "health alerts")
        assert_status(client.get("/api/verify/HC-0001"), 200, "verify HC-0001")
        assert client.get("/api/verify/HC-0001").get_json()["verified"] is True
        assert_status(client.get("/scan/HC-0001"), 200, "consumer scan")
        assert_status(client.get("/qr/HC-0001"), 200, "QR")

        # Suspicious review path: validation stays pending, then manual reject blocks trust issuance.
        resp = client.post("/api/batch/HC-0002/validate")
        assert_status(resp, 200, "revalidate suspicious")
        assert resp.get_json()["validation_status"] == "PENDING_REVIEW"
        reject = client.post("/api/batch/HC-0002/manual-reject", json={"note": "Synthetic regression-test rejection."})
        assert_status(reject, 200, "manual reject")
        assert reject.get_json()["validation_status"] == "REJECTED"
        assert reject.get_json()["record_hash"] == ""
        assert_status(client.get("/qr/HC-0002"), 404, "rejected QR")

        # A rejected batch is immutable through all evidence/image mutation paths.
        rejected_upload = client.post(
            "/api/batch/HC-0002/evidence",
            data={"pre_image": (io.BytesIO(b"not-an-image"), "bad.png")},
            content_type="multipart/form-data",
        )
        assert_status(rejected_upload, 409, "rejected evidence mutation")
        rejected_analysis = client.post(
            "/api/batch/HC-0002/analyze-image",
            data={"image": (io.BytesIO(b"not-an-image"), "bad.png")},
            content_type="multipart/form-data",
        )
        assert_status(rejected_analysis, 409, "rejected image analysis")

        # Reset for full evidence -> validate -> commit path.
        seed_demo.reset_db()
        seed_demo.seed()

        # Register a test hive and create a harvest candidate without demo evidence.
        registration = client.post("/api/hives", json={
            "hive_id": "HIVE-TEST", "beekeeper_name": "Test Keeper", "apiary_name": "Test Apiary",
            "region": "Test Region", "floral_source": "Wildflower",
        })
        assert_status(registration, 201, "register hive")
        registration_json = registration.get_json()
        assert registration_json["registration_verified"] is True
        assert registration_json["hive_id"] == "HIVE-TEST"
        assert registration_json["beekeeper_name"] == "Test Keeper"
        assert registration_json["apiary_name"] == "Test Apiary"
        assert registration_json["region"] == "Test Region"
        assert registration_json["floral_source"] == "Wildflower"
        assert registration_json["registered_payload"] == {
            "hive_id": "HIVE-TEST", "beekeeper_name": "Test Keeper", "apiary_name": "Test Apiary",
            "region": "Test Region", "floral_source": "Wildflower"
        }
        assert any(h["hive_id"] == "HIVE-TEST" for h in client.get("/api/hives").get_json())
        duplicate = client.post("/api/hives", json={
            "hive_id": "HIVE-TEST", "beekeeper_name": "Test Keeper", "apiary_name": "Test Apiary",
            "region": "Test Region", "floral_source": "Wildflower",
        })
        assert_status(duplicate, 409, "duplicate hive")
        case_duplicate = client.post("/api/hives", json={
            "hive_id": "hive-test", "beekeeper_name": "Other Keeper", "apiary_name": "Other Apiary",
            "region": "Other Region", "floral_source": "Other"
        })
        assert_status(case_duplicate, 409, "case-insensitive duplicate hive")
        canonicalized = client.post("/api/hives", json={
            "hive_id": " hive-test-2 ", "beekeeper_name": "  Test   Keeper  ", "apiary_name": " Test Apiary ",
            "region": " Test Region ", "floral_source": " Wildflower "
        })
        assert_status(canonicalized, 201, "canonicalized hive registration")
        canon = canonicalized.get_json()
        assert canon["hive_id"] == "HIVE-TEST-2"
        assert canon["beekeeper_name"] == "Test Keeper"
        assert canon["apiary_name"] == "Test Apiary"
        invalid = client.post("/api/hives", json={"hive_id": "HIVE-INVALID"})
        assert_status(invalid, 400, "invalid hive")

        # Whitespace/punctuation-only registration values must be rejected by
        # both the API validation and the same rules used by the UI.
        whitespace = client.post("/api/hives", json={
            "hive_id": "   ", "beekeeper_name": "   ", "apiary_name": "   ",
            "region": "   ", "floral_source": "   ",
        })
        assert_status(whitespace, 400, "whitespace-only hive")
        punctuation = client.post("/api/hives", json={
            "hive_id": "...", "beekeeper_name": "...", "apiary_name": "...",
            "region": "...", "floral_source": "...",
        })
        assert_status(punctuation, 400, "punctuation-only hive")
        valid_id_chars = client.post("/api/hives", json={
            "hive_id": "HIVE_TEST-VALID", "beekeeper_name": "Test Keeper",
            "apiary_name": "Test Apiary", "region": "Test Region", "floral_source": "Wildflower",
        })
        assert_status(valid_id_chars, 201, "valid hive after validation tests")
        client.post("/iot/reading", json={
            "hive_id": "HIVE-TEST", "temperature": 34.5, "humidity": 54.0,
            "weight": 30.0, "timestamp": "2026-09-27T08:00:00+00:00",
        })
        candidate = client.post("/iot/reading", json={
            "hive_id": "HIVE-TEST", "temperature": 34.5, "humidity": 54.0,
            "weight": 22.5, "timestamp": "2026-09-27T08:05:00+00:00",
        })
        assert_status(candidate, 201, "candidate harvest")
        batch_id = candidate.get_json()["harvest_event"]["batch_id"]
        assert candidate.get_json()["harvest_event"]["committed"] is False

        # Upload complete pre/post evidence and re-run the decision gate.
        pre = ROOT / "static" / "uploads" / "HC-0001" / "pre_harvest.png"
        post = ROOT / "static" / "uploads" / "HC-0001" / "post_harvest.png"
        with pre.open("rb") as f1, post.open("rb") as f2:
            upload = client.post(
                f"/api/batch/{batch_id}/evidence",
                data={"pre_image": (io.BytesIO(f1.read()), "pre.png"), "post_image": (io.BytesIO(f2.read()), "post.png")},
                content_type="multipart/form-data",
            )
        assert_status(upload, 200, "evidence upload")
        assert upload.get_json()["evidence_status"] == "COMPLETE"
        validated = client.post(f"/api/batch/{batch_id}/validate")
        assert_status(validated, 200, "validate+commit candidate")
        assert validated.get_json()["record_hash"], "candidate should commit after valid evidence + AI checks"
        assert validated.get_json()["qr_url"], "committed batch should have QR"
        assert client.get(f"/api/verify/{batch_id}").get_json()["verified"] is True

        # Custody progression remains cryptographically verifiable.
        assert_status(client.post(f"/api/batch/{batch_id}/stage", json={"stage": "Processing"}), 200, "stage advance")
        assert client.get(f"/api/verify/{batch_id}").get_json()["verified"] is True
        assert_status(client.post(f"/api/batch/{batch_id}/stage", json={"stage": "Retail"}), 400, "stage skip blocked")

        # Evidence-file deletion must break verification instead of silently
        # falling back to the stored evidence hash.
        evidence_row = client.get(f"/api/batch/{batch_id}").get_json()["evidence_items"][0]
        evidence_path = ROOT / "static" / "uploads" / evidence_row["file_name"]
        original_bytes = evidence_path.read_bytes()
        evidence_path.unlink()
        missing_evidence_check = client.get(f"/api/verify/{batch_id}").get_json()
        assert missing_evidence_check["verified"] is False, "missing evidence must fail verification"
        evidence_path.write_bytes(original_bytes)
        assert client.get(f"/api/verify/{batch_id}").get_json()["verified"] is True

        # Record tamper detection.
        client.post(f"/api/batch/{batch_id}/tamper", json={"field": "quantity_kg", "value": 999.9})
        assert client.get(f"/api/verify/{batch_id}").get_json()["verified"] is False

        # Repeated demo harvests must never surface an unhandled HTTP 500.
        for _ in range(6):
            demo = client.post("/api/demo/harvest")
            assert demo.status_code in {200, 201, 409}, f"demo harvest regression: {demo.status_code}"
            if demo.status_code == 200:
                assert demo.get_json().get("harvest_event", {}).get("idempotent") is True, "200 demo harvest response must be idempotent"
                break
            if demo.status_code == 409:
                assert demo.get_json().get("code") in {"DEMO_HIVE_DEPLETED", "DEMO_HARVEST_REJECTED"}
                break

        # Rapid repeated demo-harvest calls must be idempotent.
        seed_demo.reset_db()
        seed_demo.seed()
        first_demo = client.post("/api/demo/harvest", json={"hive_id": "HIVE-001"})
        second_demo = client.post("/api/demo/harvest", json={"hive_id": "HIVE-001"})
        assert_status(first_demo, 201, "first demo harvest")
        assert second_demo.status_code in {200, 201}, f"second demo harvest should be idempotent: {second_demo.status_code}"
        batch_rows = client.get("/api/batches").get_json()
        demo_rows = [b for b in batch_rows if b.get("hive_id") == "HIVE-001" and b.get("origin") == "demo"]
        assert len(demo_rows) == 1, f"rapid demo clicks created {len(demo_rows)} demo batches"

        # Demo reset must be immediately readable after the reset endpoint returns.
        reset = client.post("/api/demo/seed")
        assert_status(reset, 200, "demo reset endpoint")
        assert_status(client.get("/api/hives"), 200, "hives immediately after reset")
        assert_status(client.get("/api/summary"), 200, "summary immediately after reset")

    # Final clean seed for the GitHub/demo bundle.
    seed_demo.reset_db()
    seed_demo.seed()
    print("Nectar Chain v2.7.9 self-test: PASS")


if __name__ == "__main__":
    main()


# v2.7.9 UI contract checks (dependency-free)
from pathlib import Path as _Path
_ui_text = (_Path(__file__).parent / "static/js/app.js").read_text(encoding="utf-8")
_html_text = (_Path(__file__).parent / "templates/dashboard.html").read_text(encoding="utf-8")
assert "preferredDemoHiveId" in _ui_text, "New hive selection state missing"
assert "showNewHiveDemoAction" not in _ui_text, "Removed registration quick-action should stay removed"
assert 'registration-demo-action' not in _ui_text and 'registration-demo-action' not in _html_text, "Removed persistent harvest prompt should stay removed"
assert 'run-new-hive-demo' not in _ui_text and 'run-new-hive-demo' not in _html_text, "Removed quick harvest button should stay removed"
assert "/api/demo/seed" in _ui_text, "Reload demo data button handler missing"
assert "clearEventLog();" in _ui_text, "Demo reset must clear the event log"
assert "state.verifications = {};" in _ui_text, "Demo reset must clear verification state"
assert "state.preferredDemoHiveId = null;" in _ui_text, "Demo reset must clear preferred hive state"
assert 'id="seed-demo"' in _html_text, "Reload demo data button missing"
assert "location.hash = 'ledger'" in _ui_text, "Demo harvest does not route to ledger"
print("PASS: v2.7.9 registration -> harvest-events selector -> ledger + reset UI paths are wired")
