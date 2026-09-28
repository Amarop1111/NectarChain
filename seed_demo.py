"""Deterministic synthetic demo data for the Nectar Chain SIH 26021 prototype.

Run:
    python seed_demo.py --reset

The seed demonstrates the upgraded architecture:
- weight-triggered harvest detection
- environmental/context validation
- yield prediction and hive-health risk
- pre/post harvest camera evidence
- supplementary Varroa-associated visual risk screening
- verify-then-commit hash chain
- QR consumer verification

All values and images are synthetic demonstration data, not real KVIC measurements.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
RESET_LOCK = threading.Lock()

from app import (  # noqa: E402
    DB_PATH,
    DEMO_BASE_URL,
    add_custody_event,
    commit_payload,
    compute_evidence_bundle_hash,
    compute_record_hash,
    demo_evidence_bundle,
    generate_qr_for_batch,
    evidence_status,
    init_db,
    now_iso,
)


def reset_db() -> None:
    """Reset the demo store without deleting the live SQLite file.

    Keeping the same DB file avoids Windows file-lock races with another
    request connection. The in-process reset lock also protects the filesystem
    cleanup if the helper is called concurrently outside Flask.
    """
    with RESET_LOCK:
        init_db()
        conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for table in ("harvest_evidence", "stage_history", "ai_results", "readings", "health_alerts", "batches", "hives"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM sqlite_sequence")
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.close()

        qr_dir = ROOT / "static" / "qr"
        if qr_dir.exists():
            for item in qr_dir.glob("*.png"):
                try:
                    item.unlink()
                except FileNotFoundError:
                    pass
        uploads = ROOT / "static" / "uploads"
        if uploads.exists():
            for child in list(uploads.iterdir()):
                if child.is_dir():
                    import shutil
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except FileNotFoundError:
                        pass


def insert_reading(db, hive_id, batch_id, temp, humidity, weight, stamp):
    db.execute(
        "INSERT INTO readings (hive_id,batch_id,temperature,humidity,weight,timestamp) VALUES (?,?,?,?,?,?)",
        (hive_id, batch_id, temp, humidity, weight, stamp),
    )


def insert_batch(db, b):
    db.execute(
        "INSERT INTO batches (batch_id,hive_id,apiary_name,beekeeper_name,region,harvest_date,floral_source,"
        "quantity_kg,sensor_weight_before,sensor_weight_after,harvest_delta_kg,validation_status,validation_reason,"
        "ai_disease_risk,ai_predicted_yield_kg,ai_anomaly_flag,ai_confidence,evidence_hash,stage,prev_hash,record_hash,commit_sequence,"
        "committed_at,created_at,avg_temperature,avg_humidity,harvest_confidence,image_risk,image_score,image_method,health_warning,evidence_status,origin) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(b.get(k) for k in [
            "batch_id","hive_id","apiary_name","beekeeper_name","region","harvest_date","floral_source",
            "quantity_kg","sensor_weight_before","sensor_weight_after","harvest_delta_kg","validation_status",
            "validation_reason","ai_disease_risk","ai_predicted_yield_kg","ai_anomaly_flag","ai_confidence",
            "evidence_hash","stage","prev_hash","record_hash","commit_sequence","committed_at","created_at","avg_temperature",
            "avg_humidity","harvest_confidence","image_risk","image_score","image_method","health_warning","evidence_status","origin"
        ]),
    )


def finalize_committed_batch(db, batch_id: str, prev_hash: str, stage: str, stage_note: str, extra_stage: str | None = None) -> str:
    row = db.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
    b = dict(row)
    b["prev_hash"] = prev_hash
    b["evidence_hash"] = compute_evidence_bundle_hash(db, batch_id)
    b["evidence_status"] = evidence_status(db, batch_id)
    b["committed_at"] = b["committed_at"] or now_iso()
    b["commit_sequence"] = b.get("commit_sequence") or (db.execute("SELECT COALESCE(MAX(commit_sequence), 0) + 1 FROM batches").fetchone()[0])
    record_hash = compute_record_hash(b, prev_hash)
    db.execute(
        "UPDATE batches SET evidence_hash=?, evidence_status=?, prev_hash=?, record_hash=?, commit_sequence=?, committed_at=? WHERE batch_id=?",
        (b["evidence_hash"], b["evidence_status"], prev_hash, record_hash, b["commit_sequence"], b["committed_at"], batch_id),
    )
    db.execute("DELETE FROM stage_history WHERE batch_id=?", (batch_id,))
    add_custody_event(db, batch_id, stage, stage_note, b["committed_at"], anchor=record_hash)
    if extra_stage:
        add_custody_event(db, batch_id, extra_stage, f"Custody advanced to {extra_stage}.", now_iso())
    return record_hash


def seed() -> None:
    init_db()
    db = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    db.execute("PRAGMA busy_timeout = 10000")
    db.row_factory = sqlite3.Row

    hives = [
        ("HIVE-001", "Ramesh Kumar", "Nilgiris Hill Apiary", "Nilgiris, Tamil Nadu", "Eucalyptus"),
        ("HIVE-002", "Meena Devi", "Western Ghats Apiary", "Kanyakumari, Tamil Nadu", "Wildflower"),
        ("HIVE-003", "Arun Raj", "Foothill Apiary", "Idukki, Kerala", "Rubber"),
    ]
    for hive_id, beekeeper, apiary, region, floral in hives:
        db.execute(
            "INSERT INTO hives (hive_id,beekeeper_name,apiary_name,region,floral_source,registered_at,last_weight,last_reading_at) VALUES (?,?,?,?,?,?,?,?)",
            (hive_id, beekeeper, apiary, region, floral, now_iso(), None, None),
        )

    # ------------------------- HC-0001 -------------------------------------
    b1 = dict(
        batch_id="HC-0001", hive_id="HIVE-001", apiary_name="Nilgiris Hill Apiary", beekeeper_name="Ramesh Kumar",
        region="Nilgiris, Tamil Nadu", harvest_date="2026-09-06", floral_source="Eucalyptus", quantity_kg=7.4,
        sensor_weight_before=35.6, sensor_weight_after=28.2, harvest_delta_kg=7.4, validation_status="APPROVED",
        validation_reason="Approved: sensor evidence and AI checks agree.", ai_disease_risk="low", ai_predicted_yield_kg=7.7,
        ai_anomaly_flag=None, ai_confidence=.94, evidence_hash=None, stage="Harvested", prev_hash="", record_hash="", commit_sequence=1,
        committed_at=now_iso(), created_at=now_iso(), avg_temperature=34.47, avg_humidity=53.77,
        harvest_confidence=.94, image_risk="low", image_score=0.0, image_method="synthetic-demo", 
        health_warning="No significant prototype health-risk signal detected.", evidence_status="SENSOR_ONLY", origin="seed"
    )
    insert_batch(db, b1)
    insert_reading(db,"HIVE-001","HC-0001",34.3,54.0,35.6,"2026-09-06T08:55:00+00:00")
    insert_reading(db,"HIVE-001","HC-0001",34.7,53.2,34.7,"2026-09-06T09:15:00+00:00")
    insert_reading(db,"HIVE-001","HC-0001",34.4,54.1,28.2,"2026-09-06T10:00:00+00:00")
    demo_evidence_bundle(db,"HC-0001",35.6,28.2,"low")
    db.execute("UPDATE batches SET image_risk='low', image_score=0.0, image_method='pixel-heuristic', evidence_status=? WHERE batch_id='HC-0001'", (evidence_status(db,"HC-0001"),))
    b1_hash = finalize_committed_batch(db,"HC-0001","","Harvested","Approved after sensor + AI validation.")
    db.execute("INSERT INTO ai_results (batch_id,disease_risk,predicted_yield_kg,anomaly_flag,confidence,source,timestamp) VALUES (?,?,?,?,?,?,?)",
               ("HC-0001","low",7.7,None,.94,"sensor+environment+visual-demo","2026-09-06T10:01:00+00:00"))

    # ------------------------- HC-0002 -------------------------------------
    b2 = dict(
        batch_id="HC-0002", hive_id="HIVE-002", apiary_name="Western Ghats Apiary", beekeeper_name="Meena Devi",
        region="Kanyakumari, Tamil Nadu", harvest_date="2026-09-06", floral_source="Wildflower", quantity_kg=5.4,
        sensor_weight_before=29.0, sensor_weight_after=23.6, harvest_delta_kg=5.4, validation_status="PENDING_REVIEW",
        validation_reason="Medium hive-health risk detected; harvest quantity is inconsistent with AI yield prediction; visual screening requires human inspection.",
        ai_disease_risk="medium", ai_predicted_yield_kg=8.7, ai_anomaly_flag="Harvest quantity is inconsistent with AI yield prediction",
        ai_confidence=.54, evidence_hash=None, stage="Harvested", prev_hash="", record_hash="", commit_sequence=None, committed_at=None,
        created_at=now_iso(), avg_temperature=37.83, avg_humidity=68.1, harvest_confidence=.54, image_risk="medium",
        image_score=.32, image_method="pixel-heuristic", health_warning="Environmental + visual screening indicate elevated hive-health risk; inspect hive.", evidence_status="SENSOR_ONLY", origin="seed"
    )
    insert_batch(db, b2)
    insert_reading(db,"HIVE-002","HC-0002",38.1,69.0,29.0,"2026-09-06T09:05:00+00:00")
    insert_reading(db,"HIVE-002","HC-0002",37.8,68.0,27.5,"2026-09-06T09:25:00+00:00")
    insert_reading(db,"HIVE-002","HC-0002",37.6,67.3,23.6,"2026-09-06T10:05:00+00:00")
    demo_evidence_bundle(db,"HC-0002",29.0,23.6,"medium")
    health_img = db.execute("SELECT analysis_risk,analysis_score,analysis_method FROM harvest_evidence WHERE batch_id='HC-0002' AND evidence_type='health_screen' ORDER BY id DESC LIMIT 1").fetchone()
    db.execute("UPDATE batches SET image_risk=?,image_score=?,image_method=?,evidence_hash=?,evidence_status=? WHERE batch_id='HC-0002'",
               (health_img["analysis_risk"], health_img["analysis_score"], health_img["analysis_method"], compute_evidence_bundle_hash(db,"HC-0002"), evidence_status(db,"HC-0002")))
    db.execute("INSERT INTO ai_results (batch_id,disease_risk,predicted_yield_kg,anomaly_flag,confidence,source,timestamp) VALUES (?,?,?,?,?,?,?)",
               ("HC-0002","medium",8.7,"Harvest quantity is inconsistent with AI yield prediction",.54,"sensor+environment+visual-demo","2026-09-06T10:06:00+00:00"))
    db.execute("INSERT INTO health_alerts (hive_id,risk,category,message,source,timestamp) VALUES (?,?,?,?,?,?)",
               ("HIVE-002","medium","HIVE_HEALTH","Environmental + visual screening indicate elevated hive-health risk; inspect hive.","sensor+camera-demo","2026-09-06T10:06:00+00:00"))

    # ------------------------- HC-0003 -------------------------------------
    b3 = dict(
        batch_id="HC-0003", hive_id="HIVE-003", apiary_name="Foothill Apiary", beekeeper_name="Arun Raj",
        region="Idukki, Kerala", harvest_date="2026-09-06", floral_source="Rubber", quantity_kg=6.8,
        sensor_weight_before=33.2, sensor_weight_after=26.4, harvest_delta_kg=6.8, validation_status="APPROVED",
        validation_reason="Approved: sensor evidence and AI checks agree.", ai_disease_risk="low", ai_predicted_yield_kg=6.9,
        ai_anomaly_flag=None, ai_confidence=.93, evidence_hash=None, stage="Processing", prev_hash=b1_hash, record_hash="",
        committed_at=now_iso(), created_at=now_iso(), avg_temperature=34.67, avg_humidity=54.9,
        harvest_confidence=.93, image_risk="low", image_score=0.0, image_method="pixel-heuristic",
        health_warning="No significant prototype health-risk signal detected.", evidence_status="SENSOR_ONLY", origin="seed"
    )
    insert_batch(db,b3)
    insert_reading(db,"HIVE-003","HC-0003",34.6,55.2,33.2,"2026-09-06T08:40:00+00:00")
    insert_reading(db,"HIVE-003","HC-0003",34.9,54.5,31.8,"2026-09-06T09:20:00+00:00")
    insert_reading(db,"HIVE-003","HC-0003",34.5,55.0,26.4,"2026-09-06T09:55:00+00:00")
    demo_evidence_bundle(db,"HC-0003",33.2,26.4,"low")
    db.execute("UPDATE batches SET image_risk='low',image_score=0.0,image_method='pixel-heuristic',evidence_status=? WHERE batch_id='HC-0003'", (evidence_status(db,"HC-0003"),))
    b3_hash = finalize_committed_batch(db,"HC-0003",b1_hash,"Harvested","Approved after sensor + AI validation.", extra_stage="Processing")
    db.execute("INSERT INTO ai_results (batch_id,disease_risk,predicted_yield_kg,anomaly_flag,confidence,source,timestamp) VALUES (?,?,?,?,?,?,?)",
               ("HC-0003","low",6.9,None,.93,"sensor+environment+visual-demo","2026-09-06T09:56:00+00:00"))

    # Make current weights usable by the simulator.
    db.execute("UPDATE hives SET last_weight=28.2,last_reading_at=? WHERE hive_id='HIVE-001'", (now_iso(),))
    db.execute("UPDATE hives SET last_weight=23.6,last_reading_at=? WHERE hive_id='HIVE-002'", (now_iso(),))
    db.execute("UPDATE hives SET last_weight=26.4,last_reading_at=? WHERE hive_id='HIVE-003'", (now_iso(),))
    db.commit()

    generate_qr_for_batch("HC-0001", DEMO_BASE_URL or None)
    generate_qr_for_batch("HC-0003", DEMO_BASE_URL or None)
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing DB and demo QR/evidence first")
    args = parser.parse_args()
    if args.reset:
        reset_db()
    seed()
    print(f"Demo data seeded into {DB_PATH}")
    print("Approved QR batches: HC-0001, HC-0003")
    print("Manual-review batch: HC-0002")
    print("All demo values and images are synthetic.")
