"""Honey Chain / NectarNode prototype backend.

PS 26021 — Honey Chain: blockchain-based honey traceability and smart
beekeeping management.

Core prototype story:
    IoT reading -> harvest event detection -> AI validation ->
    APPROVE / MANUAL REVIEW -> hash-chain commit -> QR -> consumer verify

The current prototype uses a local SQLite hash-chain as the trust layer.
A production deployment can replace the commit layer with a permissioned
blockchain (e.g. Hyperledger Fabric) without changing the IoT/AI workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import qrcode
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, abort, g, jsonify, render_template, request, send_from_directory, has_request_context

from ai.models import predict_disease_risk_from_readings, predict_productivity
from ai.image_classifier import predict_disease_risk_from_image

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "honeychain.db"
QR_DIR = BASE_DIR / "static" / "qr"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

STAGES = ["Harvested", "Processing", "Distribution", "Retail"]
HARVEST_DROP_KG = float(os.environ.get("HARVEST_DROP_KG", "1.5"))
PROTOTYPE_VERSION = "2.7.9"
DEMO_BASE_URL = os.environ.get("HONEYCHAIN_BASE_URL", "").rstrip("/")
DEMO_CONTROLS_ENABLED = os.environ.get("NECTAR_DEMO_MODE", "1").strip().lower() not in {"0", "false", "no", "off"}

# Local prototype concurrency guards. SQLite remains the demo trust store, so
# serialize destructive demo/reset operations inside the Flask process.
DEMO_SEED_LOCK = threading.Lock()
DEMO_HARVEST_LOCK = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# Time / database helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        # A busy timeout prevents transient demo/reset contention from surfacing
        # as HTTP 500 responses. WAL is configured once during init_db(); it is
        # intentionally not changed on every request/connection.
        g.db = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 10000")
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hives (
            hive_id TEXT PRIMARY KEY,
            beekeeper_name TEXT NOT NULL,
            apiary_name TEXT NOT NULL,
            region TEXT NOT NULL,
            floral_source TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            last_weight REAL,
            last_reading_at TEXT
        );

        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id TEXT NOT NULL,
            batch_id TEXT,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            weight REAL NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (hive_id) REFERENCES hives(hive_id),
            FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
        );

        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            hive_id TEXT NOT NULL,
            apiary_name TEXT NOT NULL,
            beekeeper_name TEXT NOT NULL,
            region TEXT NOT NULL,
            harvest_date TEXT NOT NULL,
            floral_source TEXT NOT NULL,
            quantity_kg REAL NOT NULL,
            sensor_weight_before REAL NOT NULL,
            sensor_weight_after REAL NOT NULL,
            harvest_delta_kg REAL NOT NULL,
            validation_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
            validation_reason TEXT NOT NULL DEFAULT '',
            ai_disease_risk TEXT,
            ai_predicted_yield_kg REAL,
            ai_anomaly_flag TEXT,
            ai_confidence REAL,
            evidence_hash TEXT,
            stage TEXT NOT NULL DEFAULT 'Harvested',
            prev_hash TEXT NOT NULL DEFAULT '',
            record_hash TEXT NOT NULL DEFAULT '',
            commit_sequence INTEGER,
            committed_at TEXT,
            created_at TEXT NOT NULL,
            origin TEXT DEFAULT 'iot'
        );

        CREATE TABLE IF NOT EXISTS ai_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            disease_risk TEXT NOT NULL,
            predicted_yield_kg REAL NOT NULL,
            anomaly_flag TEXT,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
        );

        CREATE TABLE IF NOT EXISTS stage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            note TEXT,
            timestamp TEXT NOT NULL,
            prev_event_hash TEXT DEFAULT '',
            event_hash TEXT DEFAULT '',
            FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
        );

        CREATE TABLE IF NOT EXISTS harvest_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'camera',
            captured_at TEXT NOT NULL,
            analysis_risk TEXT,
            analysis_score REAL,
            analysis_method TEXT,
            analysis_label TEXT,
            note TEXT,
            FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
        );

        CREATE TABLE IF NOT EXISTS health_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hive_id TEXT NOT NULL,
            risk TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            source TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (hive_id) REFERENCES hives(hive_id)
        );
        """
    )

    # Backward-compatible migration for databases made by the older prototype.
    _ensure_column(conn, "batches", "hive_id", "TEXT DEFAULT ''")
    _ensure_column(conn, "batches", "sensor_weight_before", "REAL DEFAULT 0")
    _ensure_column(conn, "batches", "sensor_weight_after", "REAL DEFAULT 0")
    _ensure_column(conn, "batches", "harvest_delta_kg", "REAL DEFAULT 0")
    _ensure_column(conn, "batches", "validation_status", "TEXT DEFAULT 'PENDING_REVIEW'")
    _ensure_column(conn, "batches", "validation_reason", "TEXT DEFAULT ''")
    _ensure_column(conn, "batches", "ai_disease_risk", "TEXT")
    _ensure_column(conn, "batches", "ai_predicted_yield_kg", "REAL")
    _ensure_column(conn, "batches", "ai_anomaly_flag", "TEXT")
    _ensure_column(conn, "batches", "ai_confidence", "REAL")
    _ensure_column(conn, "batches", "avg_temperature", "REAL")
    _ensure_column(conn, "batches", "avg_humidity", "REAL")
    _ensure_column(conn, "batches", "harvest_confidence", "REAL")
    _ensure_column(conn, "batches", "image_risk", "TEXT")
    _ensure_column(conn, "batches", "image_score", "REAL")
    _ensure_column(conn, "batches", "image_method", "TEXT")
    _ensure_column(conn, "batches", "health_warning", "TEXT")
    _ensure_column(conn, "batches", "evidence_status", "TEXT DEFAULT 'SENSOR_ONLY'")
    _ensure_column(conn, "batches", "evidence_hash", "TEXT")
    _ensure_column(conn, "batches", "commit_sequence", "INTEGER")
    _ensure_column(conn, "batches", "committed_at", "TEXT")
    _ensure_column(conn, "batches", "origin", "TEXT DEFAULT 'iot'")
    # Migrate legacy hive/reading/evidence/alert tables as well. Older prototype
    # databases may predate last_weight and other fields; without these checks
    # the dashboard can fail with HTTP 500 even though the database opens.
    _ensure_column(conn, "hives", "last_weight", "REAL")
    _ensure_column(conn, "hives", "last_reading_at", "TEXT")
    _ensure_column(conn, "readings", "batch_id", "TEXT")
    _ensure_column(conn, "readings", "temperature", "REAL DEFAULT 0")
    _ensure_column(conn, "readings", "humidity", "REAL DEFAULT 0")
    _ensure_column(conn, "readings", "weight", "REAL DEFAULT 0")
    _ensure_column(conn, "readings", "timestamp", "TEXT DEFAULT ''")
    _ensure_column(conn, "ai_results", "disease_risk", "TEXT DEFAULT 'low'")
    _ensure_column(conn, "ai_results", "predicted_yield_kg", "REAL DEFAULT 0")
    _ensure_column(conn, "ai_results", "anomaly_flag", "TEXT")
    _ensure_column(conn, "ai_results", "confidence", "REAL DEFAULT 0")
    _ensure_column(conn, "ai_results", "source", "TEXT DEFAULT 'legacy'")
    _ensure_column(conn, "ai_results", "timestamp", "TEXT DEFAULT ''")
    _ensure_column(conn, "stage_history", "prev_event_hash", "TEXT DEFAULT ''")
    _ensure_column(conn, "stage_history", "event_hash", "TEXT DEFAULT ''")
    _ensure_column(conn, "harvest_evidence", "source", "TEXT DEFAULT 'camera'")
    _ensure_column(conn, "harvest_evidence", "captured_at", "TEXT DEFAULT ''")
    _ensure_column(conn, "harvest_evidence", "analysis_risk", "TEXT")
    _ensure_column(conn, "harvest_evidence", "analysis_score", "REAL")
    _ensure_column(conn, "harvest_evidence", "analysis_method", "TEXT")
    _ensure_column(conn, "harvest_evidence", "analysis_label", "TEXT")
    _ensure_column(conn, "harvest_evidence", "note", "TEXT")
    _ensure_column(conn, "health_alerts", "acknowledged", "INTEGER DEFAULT 0")
    backfill_commit_sequences(conn)

    # Registration identity is case-insensitive and whitespace-normalized.
    # This prevents logically duplicate hive IDs such as HIVE-004 and
    # hive-004 from co-existing in the local trust/telemetry store.
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_hives_hive_id_normalized "
            "ON hives(UPPER(TRIM(hive_id)))"
        )
    except sqlite3.IntegrityError:
        # Preserve legacy databases that already contain normalized duplicates;
        # the registration endpoint still rejects new duplicates explicitly.
        pass

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Evidence / visual demo helpers
# ---------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _demo_font(size: int = 24):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def generate_demo_harvest_image(batch_id: str, kind: str, weight_kg: float, output_path: Path) -> None:
    """Create a clearly synthetic camera frame for the demo.

    These images are visual evidence placeholders, not real field photographs.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (900, 560), (248, 244, 231))
    draw = ImageDraw.Draw(img)
    # honeycomb background
    for row in range(5):
        for col in range(7):
            x = 95 + col * 115 + (row % 2) * 55
            y = 150 + row * 78
            pts = [(x+32,y), (x+64,y+18), (x+64,y+54), (x+32,y+72), (x,y+54), (x,y+18)]
            draw.line(pts + [pts[0]], fill=(225, 190, 91), width=4)
    title = "PRE-HARVEST CAMERA CAPTURE" if kind == "pre_harvest" else "POST-HARVEST CAMERA CAPTURE"
    accent = (186, 107, 33)
    draw.rounded_rectangle((48, 36, 852, 118), radius=24, fill=(255, 250, 239), outline=(226, 206, 163), width=3)
    draw.text((76, 60), title, fill=accent, font=_demo_font(30))
    draw.text((76, 99), "SYNTHETIC DEMO EVIDENCE · NOT A REAL FIELD PHOTOGRAPH", fill=(105, 94, 72), font=_demo_font(17))
    # central hive frame / honey tray
    draw.rounded_rectangle((275, 150, 625, 420), radius=25, fill=(233, 176, 53), outline=(125, 89, 28), width=5)
    for x in range(320, 590, 60):
        for y in range(195, 375, 50):
            pts=[(x+18,y),(x+36,y+10),(x+36,y+30),(x+18,y+40),(x,y+30),(x,y+10)]
            draw.line(pts+[pts[0]], fill=(255, 218, 115), width=3)
    # jar/honey level cue
    if kind == "post_harvest":
        draw.rounded_rectangle((400, 190, 500, 360), radius=18, fill=(245, 199, 74), outline=(125, 89, 28), width=4)
        draw.text((418, 365), "FRAME EXTRACTED", fill=(79, 69, 49), font=_demo_font(18))
    else:
        draw.text((380, 365), "FRAME IN HIVE", fill=(79, 69, 49), font=_demo_font(18))
    draw.rounded_rectangle((650, 188, 815, 310), radius=18, fill=(255, 252, 245), outline=(211, 196, 161), width=3)
    draw.text((678, 214), "HIVE WEIGHT", fill=(96, 84, 61), font=_demo_font(18))
    draw.text((684, 250), f"{weight_kg:.1f} kg", fill=(26, 37, 54), font=_demo_font(30))
    draw.text((78, 486), "Linked to batch " + batch_id + " · timestamped · SHA-256 evidence hash", fill=(83, 98, 119), font=_demo_font(18))
    img.save(output_path, quality=92)


def generate_demo_health_image(batch_id: str, risk: str, output_path: Path) -> None:
    """Create a synthetic bee/comb-style image for the optional visual health-screen demo."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (900, 560), (245, 240, 221))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((45, 35, 855, 120), radius=22, fill=(255, 251, 238), outline=(224, 199, 145), width=3)
    draw.text((72, 60), "HIVE-HEALTH CAMERA SCREEN", fill=(45, 87, 111), font=_demo_font(30))
    draw.text((72, 99), "SYNTHETIC DEMO IMAGE · SUPPLEMENTARY RISK SCREENING", fill=(103, 91, 68), font=_demo_font(17))
    # bee-like subjects
    positions=[(220,220),(410,235),(600,210),(300,365),(530,370)]
    for idx,(cx,cy) in enumerate(positions):
        draw.ellipse((cx-48,cy-28,cx+48,cy+28), fill=(246,185,45), outline=(95,69,28), width=4)
        for off in (-20,0,20):
            draw.line((cx+off,cy-28,cx+off,cy+28), fill=(72,57,38), width=5)
        draw.ellipse((cx+35,cy-10,cx+47,cy+2), fill=(30,30,30))
        draw.arc((cx-72,cy-55,cx-10,cy+12), 180, 350, fill=(190,205,220), width=5)
        draw.arc((cx+10,cy-55,cx+72,cy+12), 190, 360, fill=(190,205,220), width=5)
    if risk in {"medium", "high"}:
        # Small dark markers emulate a consistent placeholder visual signal
        # so the bundled demo heuristic returns a visible medium/high result.
        spots = [(160,170),(455,330),(700,345)]
        for cx,cy in spots:
            draw.ellipse((cx-4,cy-4,cx+5,cy+5), fill=(28,18,12))
    label = "DEMO VISUAL SCREEN · VARROA-ASSOCIATED RISK SIGNAL" if risk in {"medium", "high"} else "DEMO VISUAL SCREEN · NO SIGNIFICANT VARROA-LIKE SIGNAL"
    draw.rounded_rectangle((210, 465, 690, 525), radius=18, fill=(255,255,255), outline=(211,196,161), width=2)
    draw.text((235, 486), label, fill=(157,80,31) if risk in {"medium", "high"} else (35,132,83), font=_demo_font(16))
    draw.text((70, 535), f"Batch {batch_id} · synthetic evidence for UI/demo validation only", fill=(91,101,115), font=_demo_font(15))
    img.save(output_path, quality=92)


def evidence_dir(batch_id: str) -> Path:
    path = UPLOAD_DIR / batch_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def add_evidence_record(db: sqlite3.Connection, batch_id: str, evidence_type: str, path: Path,
                        source: str = "camera", captured_at: str | None = None,
                        analysis: dict[str, Any] | None = None, note: str | None = None) -> dict[str, Any]:
    captured_at = captured_at or now_iso()
    sha = file_sha256(path)
    a = analysis or {}
    db.execute(
        "INSERT INTO harvest_evidence (batch_id,evidence_type,file_name,sha256,source,captured_at,analysis_risk,analysis_score,analysis_method,analysis_label,note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, evidence_type, str(path.relative_to(UPLOAD_DIR)).replace("\\", "/"), sha, source, captured_at,
         a.get("risk"), a.get("score"), a.get("method"), a.get("label"), note),
    )
    return {"evidence_type": evidence_type, "file_name": str(path.relative_to(UPLOAD_DIR)).replace("\\", "/"), "sha256": sha,
            "source": source, "captured_at": captured_at, **a}


def list_evidence(db: sqlite3.Connection, batch_id: str) -> list[dict[str, Any]]:
    rows = db.execute("SELECT * FROM harvest_evidence WHERE batch_id = ? ORDER BY id ASC", (batch_id,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        path = UPLOAD_DIR / item["file_name"]
        item["exists"] = path.exists()
        item["live_sha256"] = file_sha256(path) if path.exists() else None
        item["file_tampered"] = (not path.exists()) or (item["live_sha256"] != item["sha256"])
        item["integrity_ok"] = not item["file_tampered"]
        item["url"] = f"/static/uploads/{item['file_name']}"
        out.append(item)
    return out


def compute_evidence_bundle_hash(db: sqlite3.Connection, batch_id: str) -> str:
    """Hash the live evidence state, including missing/tampered-file state.

    A committed bundle must fail verification if an evidence file is deleted or
    changed after commitment; never fall back to the stored hash for a missing
    file.
    """
    items = []
    for item in list_evidence(db, batch_id):
        items.append({
            "evidence_type": item["evidence_type"],
            "sha256": item.get("live_sha256") if item.get("exists") else None,
            "exists": bool(item.get("exists")),
            "captured_at": item["captured_at"],
            "analysis_risk": item.get("analysis_risk"),
            "analysis_score": item.get("analysis_score"),
            "analysis_method": item.get("analysis_method"),
            "analysis_label": item.get("analysis_label"),
        })
    return _json_hash(items)


def evidence_status(db: sqlite3.Connection, batch_id: str) -> str:
    items = list_evidence(db, batch_id)
    if any(item.get("file_tampered") for item in items):
        return "INVALID"
    types = {x["evidence_type"] for x in items}
    if {"pre_harvest", "post_harvest"}.issubset(types):
        return "COMPLETE"
    if types:
        return "PARTIAL"
    return "SENSOR_ONLY"


def demo_evidence_bundle(db: sqlite3.Connection, batch_id: str, before: float, after: float, health_risk: str) -> None:
    ed = evidence_dir(batch_id)
    pre = ed / "pre_harvest.png"
    post = ed / "post_harvest.png"
    health = ed / "health_screen.png"
    if not pre.exists():
        generate_demo_harvest_image(batch_id, "pre_harvest", before, pre)
        add_evidence_record(db, batch_id, "pre_harvest", pre, source="synthetic-demo", note="Synthetic camera capture before harvest.")
    if not post.exists():
        generate_demo_harvest_image(batch_id, "post_harvest", after, post)
        add_evidence_record(db, batch_id, "post_harvest", post, source="synthetic-demo", note="Synthetic camera capture after harvest.")
    if not health.exists():
        generate_demo_health_image(batch_id, health_risk, health)
        analysis = predict_disease_risk_from_image(str(health))
        analysis["label"] = "Varroa-associated visual risk screening (demo signal)"
        add_evidence_record(db, batch_id, "health_screen", health, source="synthetic-demo", analysis=analysis,
                            note="Synthetic visual-health screen; not a diagnosis.")


def record_health_alert(db: sqlite3.Connection, hive_id: str, risk: str, category: str, message: str, source: str, timestamp: str) -> None:
    if risk not in {"medium", "high"}:
        return
    last = db.execute("SELECT timestamp FROM health_alerts WHERE hive_id = ? ORDER BY id DESC LIMIT 1", (hive_id,)).fetchone()
    if last:
        try:
            old = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
            cur = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if cur - old < timedelta(minutes=30):
                return
        except Exception:
            pass
    db.execute("INSERT INTO health_alerts (hive_id,risk,category,message,source,timestamp) VALUES (?,?,?,?,?,?)",
               (hive_id, risk, category, message, source, timestamp))


def health_summary(db: sqlite3.Connection, hive: sqlite3.Row) -> dict[str, Any]:
    rows = db.execute("SELECT temperature, humidity, weight, timestamp FROM readings WHERE hive_id = ? ORDER BY id DESC LIMIT 12", (hive["hive_id"],)).fetchall()
    if rows:
        avg_temp = sum(float(r["temperature"]) for r in rows) / len(rows)
        avg_hum = sum(float(r["humidity"]) for r in rows) / len(rows)
        sensor_risk = predict_disease_risk_from_readings(avg_temp, avg_hum, float(hive["last_weight"] or 0))
    else:
        avg_temp, avg_hum, sensor_risk = None, None, "unknown"
    image = db.execute("SELECT analysis_risk, analysis_label FROM harvest_evidence WHERE batch_id IN (SELECT batch_id FROM batches WHERE hive_id = ?) AND evidence_type = 'health_screen' ORDER BY id DESC LIMIT 1", (hive["hive_id"],)).fetchone()
    risk_levels = {"unknown":0,"low":1,"medium":2,"high":3}
    image_risk = image["analysis_risk"] if image else "unknown"
    final_risk = sensor_risk if risk_levels.get(sensor_risk,0) >= risk_levels.get(image_risk,0) else image_risk
    reasons=[]
    if sensor_risk in {"medium","high"}:
        reasons.append("environmental/weight pattern indicates elevated hive-health risk")
    if image_risk in {"medium","high"}:
        reasons.append("visual screening shows a possible Varroa-associated risk signal")
    if not reasons:
        reasons.append("no significant prototype health-risk signal detected")
    return {"risk": final_risk, "sensor_risk": sensor_risk, "image_risk": image_risk,
            "avg_temperature": round(avg_temp,2) if avg_temp is not None else None,
            "avg_humidity": round(avg_hum,2) if avg_hum is not None else None,
            "message": "; ".join(reasons),
            "early_warning": final_risk in {"medium","high"},
            "image_label": image["analysis_label"] if image else None}


# ---------------------------------------------------------------------------
# Serialization / hash-chain helpers
# ---------------------------------------------------------------------------


def _json_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def backfill_commit_sequences(conn: sqlite3.Connection) -> None:
    """Assign stable append-order sequence numbers to legacy committed batches."""
    rows = conn.execute(
        "SELECT batch_id FROM batches WHERE record_hash <> '' AND (commit_sequence IS NULL OR commit_sequence <= 0) "
        "ORDER BY COALESCE(committed_at, created_at), rowid"
    ).fetchall()
    if not rows:
        return
    start = conn.execute("SELECT COALESCE(MAX(commit_sequence), 0) FROM batches").fetchone()[0] or 0
    for offset, row in enumerate(rows, start=1):
        conn.execute("UPDATE batches SET commit_sequence = ? WHERE batch_id = ?", (start + offset, row[0]))


def next_commit_sequence(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT COALESCE(MAX(commit_sequence), 0) + 1 AS next_seq FROM batches").fetchone()
    return int(row["next_seq"])


def get_last_committed_hash(db: sqlite3.Connection) -> str:
    row = db.execute(
        "SELECT record_hash FROM batches WHERE validation_status = 'APPROVED' AND record_hash <> '' "
        "ORDER BY COALESCE(commit_sequence, 0) DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return row["record_hash"] if row else ""


def next_batch_id(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT COUNT(*) AS c FROM batches").fetchone()
    return f"HC-{row['c'] + 1:04d}"


def evidence_payload(batch: dict[str, Any], db: sqlite3.Connection | None = None) -> dict[str, Any]:
    payload = {
        "hive_id": batch["hive_id"],
        "sensor_weight_before": round(float(batch["sensor_weight_before"]), 3),
        "sensor_weight_after": round(float(batch["sensor_weight_after"]), 3),
        "harvest_delta_kg": round(float(batch["harvest_delta_kg"]), 3),
        "avg_temperature": batch.get("avg_temperature"),
        "avg_humidity": batch.get("avg_humidity"),
        "harvest_confidence": batch.get("harvest_confidence"),
        "ai_disease_risk": batch.get("ai_disease_risk"),
        "ai_predicted_yield_kg": batch.get("ai_predicted_yield_kg"),
        "ai_anomaly_flag": batch.get("ai_anomaly_flag"),
        "ai_confidence": batch.get("ai_confidence"),
        "image_risk": batch.get("image_risk"),
        "image_score": batch.get("image_score"),
        "image_method": batch.get("image_method"),
    }
    if db is not None:
        payload["evidence_items"] = [
            {"evidence_type": x["evidence_type"], "sha256": x.get("live_sha256") or x["sha256"], "captured_at": x["captured_at"],
             "analysis_risk": x.get("analysis_risk"), "analysis_score": x.get("analysis_score"),
             "analysis_method": x.get("analysis_method"), "analysis_label": x.get("analysis_label")}
            for x in list_evidence(db, batch["batch_id"])
        ]
    return payload


def commit_payload(batch: dict[str, Any], prev_hash: str) -> dict[str, Any]:
    return {
        "batch_id": batch["batch_id"],
        "hive_id": batch["hive_id"],
        "apiary_name": batch["apiary_name"],
        "beekeeper_name": batch["beekeeper_name"],
        "region": batch["region"],
        "harvest_date": batch["harvest_date"],
        "floral_source": batch["floral_source"],
        "quantity_kg": round(float(batch["quantity_kg"]), 3),
        "harvest_delta_kg": round(float(batch["harvest_delta_kg"]), 3),
        "validation_status": batch["validation_status"],
        "validation_reason": batch["validation_reason"],
        "ai_disease_risk": batch.get("ai_disease_risk"),
        "ai_predicted_yield_kg": batch.get("ai_predicted_yield_kg"),
        "ai_anomaly_flag": batch.get("ai_anomaly_flag"),
        "ai_confidence": batch.get("ai_confidence"),
        "avg_temperature": batch.get("avg_temperature"),
        "avg_humidity": batch.get("avg_humidity"),
        "harvest_confidence": batch.get("harvest_confidence"),
        "image_risk": batch.get("image_risk"),
        "image_score": batch.get("image_score"),
        "image_method": batch.get("image_method"),
        "evidence_status": batch.get("evidence_status"),
        "evidence_hash": batch.get("evidence_hash"),
        "committed_at": batch.get("committed_at"),
        "prev_hash": prev_hash,
    }


def compute_record_hash(batch: dict[str, Any], prev_hash: str) -> str:
    return _json_hash(commit_payload(batch, prev_hash))


def batch_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    return d


def custody_event_hash(batch_id: str, stage: str, note: str, timestamp: str, prev_event_hash: str) -> str:
    return _json_hash({
        "batch_id": batch_id,
        "stage": stage,
        "note": note,
        "timestamp": timestamp,
        "prev_event_hash": prev_event_hash,
    })


def get_last_custody_hash(db: sqlite3.Connection, batch_id: str) -> str:
    row = db.execute(
        "SELECT event_hash FROM stage_history WHERE batch_id = ? ORDER BY id DESC LIMIT 1", (batch_id,)
    ).fetchone()
    return row["event_hash"] if row and row["event_hash"] else ""


def add_custody_event(db: sqlite3.Connection, batch_id: str, stage: str, note: str, timestamp: str, anchor: str | None = None) -> str:
    prev = get_last_custody_hash(db, batch_id) or (anchor or "")
    event_hash = custody_event_hash(batch_id, stage, note, timestamp, prev)
    db.execute(
        "INSERT INTO stage_history (batch_id, stage, note, timestamp, prev_event_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?)",
        (batch_id, stage, note, timestamp, prev, event_hash),
    )
    return event_hash


def verify_custody(db: sqlite3.Connection, batch_id: str, anchor: str) -> dict[str, Any]:
    batch = db.execute("SELECT stage FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if batch is None:
        return {"verified": False, "broken_at": None, "reason": "Batch not found."}
    rows = db.execute(
        "SELECT * FROM stage_history WHERE batch_id = ? ORDER BY id ASC", (batch_id,)
    ).fetchall()
    if not rows:
        return {"verified": False, "broken_at": None, "reason": "Custody trail is missing."}

    previous = anchor
    previous_index = -1
    for row in rows:
        stage = row["stage"]
        if stage not in STAGES:
            return {"verified": False, "broken_at": stage, "reason": "Custody stage is invalid."}
        stage_index = STAGES.index(stage)
        if stage_index <= previous_index:
            return {"verified": False, "broken_at": stage, "reason": "Custody stages are not strictly progressing."}
        expected = custody_event_hash(row["batch_id"], stage, row["note"] or "", row["timestamp"], previous)
        if row["prev_event_hash"] != previous or row["event_hash"] != expected:
            return {"verified": False, "broken_at": stage, "reason": "Custody event hash is broken."}
        previous = row["event_hash"]
        previous_index = stage_index

    if batch["stage"] != rows[-1]["stage"]:
        return {"verified": False, "broken_at": batch["stage"], "reason": "Current custody stage does not match the custody trail."}

    return {"verified": True, "broken_at": None, "reason": "Custody trail is intact."}


def verify_chain(db: sqlite3.Connection, upto_batch_id: str | None = None) -> dict[str, Any]:
    rows = db.execute(
        "SELECT * FROM batches WHERE validation_status = 'APPROVED' AND record_hash <> '' "
        "ORDER BY COALESCE(commit_sequence, 0) ASC, rowid ASC"
    ).fetchall()
    previous_hash = ""
    expected_sequence = 1
    for row in rows:
        b = batch_dict(row)
        seq = b.get("commit_sequence")
        if seq is not None and int(seq) != expected_sequence:
            return {
                "verified": False,
                "broken_at": b["batch_id"],
                "reason": "Commit sequence is broken.",
            }
        expected = compute_record_hash(b, previous_hash)
        if b["prev_hash"] != previous_hash:
            return {
                "verified": False,
                "broken_at": b["batch_id"],
                "reason": "Previous-hash link is broken.",
            }
        if expected != b["record_hash"]:
            return {
                "verified": False,
                "broken_at": b["batch_id"],
                "reason": "Record hash does not match committed data.",
            }
        previous_hash = b["record_hash"]
        expected_sequence += 1
        if upto_batch_id and b["batch_id"] == upto_batch_id:
            break
    return {"verified": True, "broken_at": None, "reason": "Chain is intact."}


def compute_trust_score(batch: dict[str, Any]) -> int | None:
    if batch.get("validation_status") != "APPROVED":
        return None
    score = 100
    risk = batch.get("ai_disease_risk")
    score -= {"low": 0, "medium": 15, "high": 35}.get(risk, 10)
    if batch.get("ai_anomaly_flag"):
        score -= 25
    if batch.get("evidence_hash"):
        score += 0
    return max(0, min(100, score))


def enrich_batch(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    batch = batch_dict(row)
    readings = db.execute(
        "SELECT temperature, humidity, weight, timestamp FROM readings WHERE batch_id = ? ORDER BY id ASC",
        (batch["batch_id"],),
    ).fetchall()
    batch["readings"] = [dict(r) for r in readings]
    batch["stage_history"] = [
        dict(r)
        for r in db.execute(
            "SELECT stage, note, timestamp, prev_event_hash, event_hash FROM stage_history WHERE batch_id = ? ORDER BY id ASC",
            (batch["batch_id"],),
        ).fetchall()
    ]
    batch["evidence_items"] = list_evidence(db, batch["batch_id"])
    batch["evidence_status"] = evidence_status(db, batch["batch_id"])
    batch["live_evidence_hash"] = compute_evidence_bundle_hash(db, batch["batch_id"])
    evidence_types = {item.get("evidence_type") for item in batch["evidence_items"]}
    batch["evidence_completeness"] = 100 if {"pre_harvest", "post_harvest"}.issubset(evidence_types) else (50 if evidence_types else 0)
    batch["trust_score"] = compute_trust_score(batch)
    batch["qr_url"] = f"/qr/{batch['batch_id']}" if batch["record_hash"] else None
    batch["commit_sequence"] = batch.get("commit_sequence")
    batch["scan_url"] = f"/scan/{batch['batch_id']}" if batch["record_hash"] else None
    chain = verify_chain(db, batch["batch_id"]) if batch["record_hash"] else {"verified": False, "reason": "Not committed yet."}
    custody = verify_custody(db, batch["batch_id"], batch["record_hash"]) if batch["record_hash"] else {"verified": False, "reason": "Not committed yet."}
    batch["chain_verified"] = bool(chain["verified"])
    batch["custody_verified"] = bool(custody["verified"])
    return batch


# ---------------------------------------------------------------------------
# AI / verification pipeline
# ---------------------------------------------------------------------------


def latest_hive_context(db: sqlite3.Connection, hive_id: str, before_event_weight: float) -> list[sqlite3.Row]:
    rows = db.execute(
        "SELECT temperature, humidity, weight, timestamp FROM readings WHERE hive_id = ? "
        "ORDER BY id DESC LIMIT 12",
        (hive_id,),
    ).fetchall()
    return list(reversed(rows))


def validate_harvest(
    db: sqlite3.Connection,
    hive: sqlite3.Row,
    previous_weight: float,
    current_weight: float,
    harvest_time: str,
) -> dict[str, Any]:
    delta = round(previous_weight - current_weight, 3)
    context = latest_hive_context(db, hive["hive_id"], previous_weight)
    if context:
        avg_temp = sum(float(r["temperature"]) for r in context) / len(context)
        avg_humidity = sum(float(r["humidity"]) for r in context) / len(context)
    else:
        avg_temp, avg_humidity = 34.0, 55.0

    sensor_health_risk = predict_disease_risk_from_readings(avg_temp, avg_humidity, previous_weight)
    predicted_yield = predict_productivity(avg_temp, avg_humidity, previous_weight)

    anomaly_flag = None
    reasons: list[str] = []
    if delta < HARVEST_DROP_KG:
        anomaly_flag = "Weight drop is too small to confirm a harvest event"
        reasons.append(anomaly_flag)
    elif predicted_yield > 0 and abs(delta - predicted_yield) / max(predicted_yield, 0.1) > 0.45:
        anomaly_flag = "Harvest quantity is inconsistent with AI yield prediction"
        reasons.append(anomaly_flag)

    if sensor_health_risk == "high":
        reasons.append("High hive-health risk detected from recent environmental/weight patterns")
    elif sensor_health_risk == "medium":
        reasons.append("Medium hive-health risk detected; human inspection recommended")

    approved = sensor_health_risk == "low" and anomaly_flag is None
    confidence = 0.92
    if sensor_health_risk == "medium":
        confidence -= 0.18
    elif sensor_health_risk == "high":
        confidence -= 0.35
    if anomaly_flag:
        confidence -= 0.20
    confidence = round(max(0.2, confidence), 2)

    return {
        "harvest_delta_kg": delta,
        "disease_risk": sensor_health_risk,
        "predicted_yield_kg": round(float(predicted_yield), 2),
        "anomaly_flag": anomaly_flag,
        "confidence": confidence,
        "harvest_confidence": confidence,
        "status": "APPROVED" if approved else "PENDING_REVIEW",
        "reason": "Approved: sensor evidence and AI checks agree." if approved else "; ".join(reasons) or "Manual review required.",
        "avg_temperature": round(avg_temp, 2),
        "avg_humidity": round(avg_humidity, 2),
        "health_warning": "; ".join(reasons) if reasons else "No significant health-risk indicator detected.",
        "evaluated_at": harvest_time,
    }


def apply_validation_result(db: sqlite3.Connection, batch_id: str, validation: dict[str, Any], *, require_complete_evidence: bool = True) -> dict[str, Any]:
    """Persist validation results and enforce the evidence gate for commitment."""
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise ValueError("Batch not found")
    image = db.execute(
        "SELECT analysis_risk, analysis_score, analysis_method FROM harvest_evidence "
        "WHERE batch_id = ? AND evidence_type = 'health_screen' ORDER BY id DESC LIMIT 1",
        (batch_id,),
    ).fetchone()
    image_risk = image["analysis_risk"] if image else row["image_risk"]
    image_score = image["analysis_score"] if image else row["image_score"]
    image_method = image["analysis_method"] if image else row["image_method"]
    reasons = []
    if validation["reason"] and validation["status"] != "APPROVED":
        reasons.append(validation["reason"])
    if image_risk in {"medium", "high"}:
        reasons.append("Visual health screening raised an elevated hive-health risk signal; expert inspection recommended.")
    evidence_state = evidence_status(db, batch_id)
    if require_complete_evidence and evidence_state != "COMPLETE":
        reasons.append("Complete pre-harvest and post-harvest evidence is required before commitment.")
    approved = validation["status"] == "APPROVED" and image_risk not in {"medium", "high"} and (not require_complete_evidence or evidence_state == "COMPLETE")
    status = "APPROVED" if approved else "PENDING_REVIEW"
    reason = "Approved: sensor, visual and evidence checks agree." if approved else "; ".join(dict.fromkeys(reasons))
    health_warning = validation.get("health_warning") or "No significant health-risk indicator detected."
    if image_risk in {"medium", "high"}:
        health_warning = "Visual screening indicates elevated hive-health risk; beekeeper/expert confirmation remains required."
    db.execute(
        "UPDATE batches SET validation_status=?, validation_reason=?, ai_disease_risk=?, ai_predicted_yield_kg=?, "
        "ai_anomaly_flag=?, ai_confidence=?, avg_temperature=?, avg_humidity=?, harvest_confidence=?, image_risk=?, image_score=?, "
        "image_method=?, health_warning=?, evidence_status=? WHERE batch_id=?",
        (status, reason, validation["disease_risk"], validation["predicted_yield_kg"], validation["anomaly_flag"],
         validation["confidence"], validation["avg_temperature"], validation["avg_humidity"], validation["harvest_confidence"],
         image_risk, image_score, image_method, health_warning, evidence_state, batch_id),
    )
    existing = db.execute("SELECT id FROM ai_results WHERE batch_id=? ORDER BY id DESC LIMIT 1", (batch_id,)).fetchone()
    if existing:
        db.execute(
            "UPDATE ai_results SET disease_risk=?, predicted_yield_kg=?, anomaly_flag=?, confidence=?, source=?, timestamp=? WHERE id=?",
            (validation["disease_risk"], validation["predicted_yield_kg"], validation["anomaly_flag"], validation["confidence"],
             "sensor+environment+visual", validation["evaluated_at"], existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO ai_results (batch_id,disease_risk,predicted_yield_kg,anomaly_flag,confidence,source,timestamp) VALUES (?,?,?,?,?,?,?)",
            (batch_id, validation["disease_risk"], validation["predicted_yield_kg"], validation["anomaly_flag"], validation["confidence"],
             "sensor+environment+visual", validation["evaluated_at"]),
        )
    db.commit()
    return enrich_batch(db, db.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone())


def revalidate_batch(db: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise ValueError("Batch not found")
    if row["record_hash"]:
        raise ValueError("Committed batches are immutable; verification is separate from re-validation.")
    if row["validation_status"] == "REJECTED":
        raise ValueError("Rejected batches cannot be revalidated in-place; create a new harvest record if needed.")
    hive = db.execute("SELECT * FROM hives WHERE hive_id=?", (row["hive_id"],)).fetchone()
    if hive is None:
        raise ValueError("Hive not found")
    validation = validate_harvest(db, hive, float(row["sensor_weight_before"]), float(row["sensor_weight_after"]), now_iso())
    enriched = apply_validation_result(db, batch_id, validation, require_complete_evidence=True)
    if enriched["validation_status"] == "APPROVED":
        return commit_approved_batch(db, batch_id)
    return enriched


def manual_review_decision(db: sqlite3.Connection, batch_id: str, decision: str, note: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise ValueError("Batch not found")
    if row["record_hash"]:
        raise ValueError("Committed batches cannot be manually re-decided.")
    if row["validation_status"] == "REJECTED":
        raise ValueError("Batch is already rejected.")
    if decision == "reject":
        reason = note or "Manual review rejected the harvest candidate; no ledger record or QR generated."
        db.execute("UPDATE batches SET validation_status='REJECTED', validation_reason=?, health_warning=? WHERE batch_id=?",
                   (reason, "Rejected during manual review; no trusted record was committed.", batch_id))
        db.commit()
        return enrich_batch(db, db.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone())
    if evidence_status(db, batch_id) != "COMPLETE":
        raise ValueError("Complete pre-harvest and post-harvest evidence is required before manual approval.")
    original_reason = row["validation_reason"] or "AI flagged the batch for manual review."
    approval_reason = f"Manual review approved. {note or 'Reviewer inspected the evidence.'} Original validation: {original_reason}"
    image = db.execute("SELECT analysis_risk, analysis_score, analysis_method FROM harvest_evidence WHERE batch_id=? AND evidence_type='health_screen' ORDER BY id DESC LIMIT 1", (batch_id,)).fetchone()
    db.execute(
        "UPDATE batches SET validation_status='APPROVED', validation_reason=?, image_risk=?, image_score=?, image_method=? WHERE batch_id=?",
        (approval_reason, image["analysis_risk"] if image else row["image_risk"], image["analysis_score"] if image else row["image_score"],
         image["analysis_method"] if image else row["image_method"], batch_id),
    )
    db.commit()
    return commit_approved_batch(db, batch_id)


def commit_approved_batch(db: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise ValueError("Batch not found")
    batch = batch_dict(row)
    if batch["validation_status"] != "APPROVED":
        raise ValueError("Only approved batches can be committed. Use validation or manual review first.")
    if batch["record_hash"]:
        return enrich_batch(db, row)

    current_evidence_status = evidence_status(db, batch_id)
    if current_evidence_status != "COMPLETE":
        raise ValueError("Complete pre-harvest and post-harvest evidence is required before ledger commitment.")

    committed_at = now_iso()
    batch["committed_at"] = committed_at
    batch["evidence_status"] = current_evidence_status
    current_evidence_hash = compute_evidence_bundle_hash(db, batch_id)
    batch["evidence_hash"] = current_evidence_hash
    prev_hash = get_last_committed_hash(db)
    commit_sequence = next_commit_sequence(db)
    record_hash = compute_record_hash(batch, prev_hash)

    db.execute(
        "UPDATE batches SET evidence_hash = ?, evidence_status = ?, committed_at = ?, commit_sequence = ?, prev_hash = ?, record_hash = ? WHERE batch_id = ?",
        (current_evidence_hash, current_evidence_status, committed_at, commit_sequence, prev_hash, record_hash, batch_id),
    )
    note = batch["validation_reason"] or "AI validation passed. Batch committed to the tamper-evident hash-chain."
    add_custody_event(db, batch_id, STAGES[0], note, committed_at, anchor=record_hash)
    db.commit()
    base_url = current_base_url()
    generate_qr_for_batch(batch_id, base_url=base_url)
    fresh = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    return enrich_batch(db, fresh)


# ---------------------------------------------------------------------------
# Hive / IoT endpoints
# ---------------------------------------------------------------------------

@app.route("/api/version", methods=["GET"])
def api_version():
    return jsonify({"version": PROTOTYPE_VERSION, "service": "nectar-chain", "registration_round_trip": True})


@app.route("/api/hives", methods=["GET"])
def api_hives():
    db = get_db()
    rows = db.execute("SELECT * FROM hives ORDER BY hive_id").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["health"] = health_summary(db, row)
        except Exception as exc:
            # One malformed/legacy hive must not blank the entire dashboard.
            item["health"] = {
                "risk": "unknown", "sensor_risk": "unknown", "image_risk": "unknown",
                "avg_temperature": None, "avg_humidity": None,
                "message": "Health context unavailable; readings can still be collected.",
                "early_warning": False, "image_label": None,
                "error": str(exc),
            }
        result.append(item)
    return jsonify(result)


@app.route("/api/hives", methods=["POST"])
def register_hive():
    data = request.get_json(silent=True) or {}
    required = ["hive_id", "beekeeper_name", "apiary_name", "region", "floral_source"]
    cleaned = {k: re.sub(r"\s+", " ", str(data.get(k, "")).strip()) for k in required}
    # Hive IDs are canonicalized so the same physical hive cannot appear under
    # visually different case variants.
    cleaned["hive_id"] = cleaned["hive_id"].upper()
    missing = [k for k in required if not cleaned[k]]
    if missing:
        return jsonify({"error": "Fill all five hive registration fields."}), 400

    # Reject whitespace/punctuation-only values server-side. The browser
    # performs the same check for immediate feedback, but the API must remain
    # authoritative because it can be called directly.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}", cleaned["hive_id"]):
        return jsonify({
            "error": "Invalid Hive ID. Use 3-64 letters, numbers, hyphens, or underscores, starting with a letter or number."
        }), 400
    for field in ("beekeeper_name", "apiary_name", "region", "floral_source"):
        if not any(ch.isalnum() for ch in cleaned[field]):
            return jsonify({"error": f"{field.replace('_', ' ').title()} must contain letters or numbers."}), 400
        if len(cleaned[field]) > 120:
            return jsonify({"error": f"{field.replace('_', ' ').title()} is too long (max 120 characters)."}), 400
    db = get_db()
    try:
        # Explicit normalized duplicate check gives a clean API error even when
        # the database was created before the case-insensitive unique index.
        existing = db.execute(
            "SELECT hive_id FROM hives WHERE UPPER(TRIM(hive_id)) = UPPER(TRIM(?)) LIMIT 1",
            (cleaned["hive_id"],),
        ).fetchone()
        if existing is not None:
            return jsonify({"error": "Hive ID already exists. Use a unique Hive ID."}), 409

        db.execute(
            "INSERT INTO hives (hive_id, beekeeper_name, apiary_name, region, floral_source, registered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cleaned["hive_id"], cleaned["beekeeper_name"], cleaned["apiary_name"], cleaned["region"], cleaned["floral_source"], now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "Hive ID already exists. Use a unique Hive ID."}), 409

    row = db.execute("SELECT * FROM hives WHERE hive_id = ?", (cleaned["hive_id"],)).fetchone()
    if row is None:
        db.rollback()
        return jsonify({"error": "Registration could not be verified after save."}), 500

    # Database round-trip guard: never report a registration as successful if
    # the persisted values differ from the canonical request values.
    saved = {field: row[field] for field in required}
    expected = {field: cleaned[field] for field in required}
    if saved != expected:
        db.execute("DELETE FROM hives WHERE hive_id = ?", (cleaned["hive_id"],))
        db.commit()
        return jsonify({"error": "Registration integrity check failed; no hive was created."}), 500

    created = dict(row)
    try:
        created["health"] = health_summary(db, row)
    except Exception as exc:
        # The registration itself is already committed. Never turn a health
        # summary problem into a misleading registration HTTP 500.
        created["health"] = {
            "risk": "unknown", "sensor_risk": "unknown", "image_risk": "unknown",
            "avg_temperature": None, "avg_humidity": None,
            "message": "Health context unavailable; readings can still be collected.",
            "early_warning": False, "image_label": None, "error": str(exc),
        }
    created["registration_verified"] = True
    created["registered_payload"] = expected
    return jsonify(created), 201


def process_iot_reading(db: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    required = ["hive_id", "temperature", "humidity", "weight"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing fields: {missing}")
    hive = db.execute("SELECT * FROM hives WHERE hive_id = ?", (data["hive_id"],)).fetchone()
    if hive is None:
        raise LookupError("Unknown hive_id. Register the hive first.")

    timestamp = data.get("timestamp") or now_iso()
    previous_weight = hive["last_weight"]
    current_weight = float(data["weight"])
    temperature = float(data["temperature"])
    humidity = float(data["humidity"])
    if not (-20 <= temperature <= 80):
        raise ValueError("temperature is outside supported range")
    if not (0 <= humidity <= 100):
        raise ValueError("humidity must be between 0 and 100")
    if current_weight <= 0:
        raise ValueError("weight must be positive")

    cur = db.execute(
        "INSERT INTO readings (hive_id, batch_id, temperature, humidity, weight, timestamp) VALUES (?, NULL, ?, ?, ?, ?)",
        (data["hive_id"], temperature, humidity, current_weight, timestamp),
    )
    reading_id = cur.lastrowid
    db.execute("UPDATE hives SET last_weight = ?, last_reading_at = ? WHERE hive_id = ?", (current_weight, timestamp, data["hive_id"]))

    current_health_risk = predict_disease_risk_from_readings(temperature, humidity, current_weight)
    if current_health_risk in {"medium", "high"}:
        record_health_alert(db, data["hive_id"], current_health_risk, "HIVE_HEALTH", "Elevated hive-health risk from environmental/weight pattern; inspect hive.", "sensor-baseline-ai", timestamp)

    event = None
    if previous_weight is not None and (float(previous_weight) - current_weight) >= HARVEST_DROP_KG:
        validation = validate_harvest(db, hive, float(previous_weight), current_weight, timestamp)
        batch_id = next_batch_id(db)
        db.execute(
            "INSERT INTO batches (batch_id, hive_id, apiary_name, beekeeper_name, region, harvest_date, floral_source, "
            "quantity_kg, sensor_weight_before, sensor_weight_after, harvest_delta_kg, validation_status, validation_reason, "
            "ai_disease_risk, ai_predicted_yield_kg, ai_anomaly_flag, ai_confidence, avg_temperature, avg_humidity, harvest_confidence, "
            "health_warning, evidence_status, stage, created_at, origin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id, hive["hive_id"], hive["apiary_name"], hive["beekeeper_name"], hive["region"], timestamp[:10], hive["floral_source"],
                validation["harvest_delta_kg"], float(previous_weight), current_weight, validation["harvest_delta_kg"], "PENDING_REVIEW",
                validation["reason"], validation["disease_risk"], validation["predicted_yield_kg"], validation["anomaly_flag"],
                validation["confidence"], validation["avg_temperature"], validation["avg_humidity"], validation["harvest_confidence"],
                validation["health_warning"], "SENSOR_ONLY", STAGES[0], timestamp, "demo" if data.get("demo_mode") else "iot",
            ),
        )
        db.execute("UPDATE readings SET batch_id = ? WHERE id = ?", (batch_id, reading_id))
        db.execute(
            "INSERT INTO ai_results (batch_id, disease_risk, predicted_yield_kg, anomaly_flag, confidence, source, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (batch_id, validation["disease_risk"], validation["predicted_yield_kg"], validation["anomaly_flag"], validation["confidence"], "sensor+baseline-ai", timestamp),
        )
        db.commit()

        if data.get("demo_mode"):
            demo_evidence_bundle(db, batch_id, float(previous_weight), current_weight, validation["disease_risk"])
            # Re-run the decision gate after evidence collection. This is the core Verify-then-Commit path.
            enriched = revalidate_batch(db, batch_id)
            validation_status = enriched["validation_status"]
            event = {
                "batch_id": batch_id,
                "harvest_delta_kg": validation["harvest_delta_kg"],
                "validation_status": validation_status,
                "reason": enriched["validation_reason"],
                "ai": {
                    "disease_risk": enriched["ai_disease_risk"],
                    "predicted_yield_kg": enriched["ai_predicted_yield_kg"],
                    "anomaly_flag": enriched["ai_anomaly_flag"],
                    "confidence": enriched["ai_confidence"],
                },
                "evidence_status": enriched["evidence_status"],
                "committed": bool(enriched["record_hash"]),
            }
            if enriched["record_hash"]:
                event["record_hash"] = enriched["record_hash"]
                event["qr_url"] = enriched["qr_url"]
            else:
                event["manual_review_required"] = True
        else:
            # Real IoT traffic must still collect camera evidence before trust-layer commitment.
            db.execute("UPDATE batches SET validation_status='PENDING_REVIEW', validation_reason=? WHERE batch_id=?",
                        ("Harvest candidate detected; awaiting complete pre/post harvest evidence before commitment.", batch_id))
            db.commit()
            event = {
                "batch_id": batch_id,
                "harvest_delta_kg": validation["harvest_delta_kg"],
                "validation_status": "PENDING_REVIEW",
                "reason": "Harvest candidate detected; awaiting complete pre/post harvest evidence before commitment.",
                "ai": validation,
                "evidence_status": "SENSOR_ONLY",
                "committed": False,
                "manual_review_required": True,
            }

    return {
        "reading": {
            "hive_id": data["hive_id"], "temperature": temperature, "humidity": humidity, "weight": current_weight,
            "health_risk": current_health_risk, "timestamp": timestamp,
        },
        "harvest_event": event,
    }


@app.route("/iot/reading", methods=["POST"])
def ingest_iot_reading():
    data = request.get_json(silent=True) or {}
    db = get_db()
    try:
        result = process_iot_reading(db, data)
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    db.commit()
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

@app.route("/api/demo/seed", methods=["POST"])
def demo_seed():
    """Reset the local DB and load deterministic synthetic demo data safely."""
    if not DEMO_CONTROLS_ENABLED:
        return jsonify({"error": "Demo controls are disabled on this deployment."}), 403
    from seed_demo import reset_db, seed
    with DEMO_SEED_LOCK:
        # The current request connection must be closed before the seed script
        # removes/recreates the SQLite file. Otherwise WAL/locking can race the
        # immediate dashboard refresh that follows the reset.
        close_db()
        reset_db()
        seed()
    return jsonify({"message": "Synthetic demo data loaded.", "approved": ["HC-0001", "HC-0003"], "manual_review": ["HC-0002"]}), 200


@app.route("/api/demo/harvest", methods=["POST"])
def demo_harvest():
    """Trigger a deterministic demo harvest for a selected registered hive.

    Registration and harvest are intentionally separate. The endpoint is made
    idempotent for rapid repeated demo clicks so one UI action cannot create
    two harvest records for the same hive.
    """
    if not DEMO_CONTROLS_ENABLED:
        return jsonify({"error": "Demo controls are disabled on this deployment."}), 403
    payload = request.get_json(silent=True) or {}
    hive_id = str(payload.get("hive_id") or "HIVE-001").strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}", hive_id):
        return jsonify({"error": "Invalid hive ID for demo harvest."}), 400

    with DEMO_HARVEST_LOCK:
        db = get_db()
        hive = db.execute("SELECT * FROM hives WHERE UPPER(TRIM(hive_id)) = UPPER(TRIM(?))", (hive_id,)).fetchone()
        if hive is None:
            return jsonify({"error": f"{hive_id} not found. Register the hive first."}), 404

        # Rapid double-click protection: if this hive already received a demo
        # harvest in the last 8 seconds, return that batch instead of creating
        # another one. This is intentionally scoped to origin='demo'.
        latest = db.execute(
            "SELECT * FROM batches WHERE hive_id=? AND origin='demo' ORDER BY rowid DESC LIMIT 1",
            (hive_id,),
        ).fetchone()
        if latest is not None:
            try:
                created = datetime.fromisoformat((latest["created_at"] or "").replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - created
            except Exception:
                age = timedelta(seconds=999)
            if age.total_seconds() <= 8:
                enriched = enrich_batch(db, latest)
                return jsonify({
                    "hive_id": hive_id,
                    "reading": {
                        "hive_id": hive_id,
                        "temperature": enriched.get("avg_temperature"),
                        "humidity": enriched.get("avg_humidity"),
                        "weight": enriched.get("sensor_weight_after"),
                        "timestamp": latest["created_at"],
                    },
                    "harvest_event": {
                        "batch_id": latest["batch_id"],
                        "harvest_delta_kg": latest["harvest_delta_kg"],
                        "validation_status": latest["validation_status"],
                        "reason": latest["validation_reason"],
                        "ai": {
                            "disease_risk": latest["ai_disease_risk"],
                            "predicted_yield_kg": latest["ai_predicted_yield_kg"],
                            "anomaly_flag": latest["ai_anomaly_flag"],
                            "confidence": latest["ai_confidence"],
                        },
                        "evidence_status": enriched.get("evidence_status"),
                        "committed": bool(latest["record_hash"]),
                        "manual_review_required": not bool(latest["record_hash"]),
                        "idempotent": True,
                    },
                }), 200

        try:
            ts = now_iso()
            if hive["last_weight"] is None:
                baseline = 35.0
                first = process_iot_reading(db, {
                    "hive_id": hive_id, "temperature": 34.4, "humidity": 54.0,
                    "weight": baseline, "timestamp": ts
                })
                before = baseline
            else:
                before = float(hive["last_weight"])
                if before <= 0:
                    return jsonify({
                        "error": "Demo hive weight is unavailable. Reload demo data or add a fresh sensor reading.",
                        "code": "DEMO_HIVE_INVALID_WEIGHT",
                        "hive_id": hive_id,
                    }), 409
                first = process_iot_reading(db, {
                    "hive_id": hive_id, "temperature": 34.4, "humidity": 54.0,
                    "weight": round(before + 0.1, 2), "timestamp": ts
                })

            target_after = round(before - 5.9, 2)
            if target_after <= 0 or (before - target_after) < HARVEST_DROP_KG:
                db.rollback()
                return jsonify({
                    "error": "Demo hive weight is too low for another synthetic harvest. Reload demo data or use another hive.",
                    "code": "DEMO_HIVE_DEPLETED",
                    "hive_id": hive_id,
                    "current_weight": before,
                }), 409

            second = process_iot_reading(db, {
                "hive_id": hive_id, "temperature": 34.5, "humidity": 54.0,
                "weight": target_after, "timestamp": now_iso(), "demo_mode": True
            })
        except (ValueError, LookupError) as exc:
            db.rollback()
            return jsonify({"error": str(exc), "code": "DEMO_HARVEST_REJECTED", "hive_id": hive_id}), 409
        return jsonify({"hive_id": hive_id, "baseline_reading": first["reading"], **second}), 201


# ---------------------------------------------------------------------------
# Batch APIs
# ---------------------------------------------------------------------------

@app.route("/api/batches", methods=["GET"])
def api_batches():
    db = get_db()
    rows = db.execute("SELECT * FROM batches ORDER BY rowid ASC").fetchall()
    result = []
    for row in rows:
        try:
            result.append(enrich_batch(db, row))
        except Exception as exc:
            # Keep the dashboard usable if a legacy/corrupt batch exists; surface
            # the issue with an explicit record instead of failing the whole API.
            fallback = dict(row)
            fallback.update({
                "readings": [], "stage_history": [], "evidence_items": [],
                "evidence_status": fallback.get("evidence_status") or "SENSOR_ONLY",
                "live_evidence_hash": "", "trust_score": None,
                "qr_url": None, "scan_url": None,
                "chain_verified": False, "custody_verified": False,
                "api_error": str(exc),
            })
            result.append(fallback)
    return jsonify(result)


@app.route("/api/batch/<batch_id>", methods=["GET"])
def api_batch(batch_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    return jsonify(enrich_batch(db, row))


@app.route("/api/batch/<batch_id>/validate", methods=["POST"])
def validate_batch_endpoint(batch_id: str):
    db = get_db()
    try:
        result = revalidate_batch(db, batch_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 200


@app.route("/api/batch/<batch_id>/manual-approve", methods=["POST"])
def manual_approve(batch_id: str):
    db = get_db()
    data = request.get_json(silent=True) or {}
    try:
        result = manual_review_decision(db, batch_id, "approve", data.get("note") or "Reviewer inspected the evidence and approved the harvest.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 200


@app.route("/api/batch/<batch_id>/manual-reject", methods=["POST"])
def manual_reject(batch_id: str):
    db = get_db()
    data = request.get_json(silent=True) or {}
    try:
        result = manual_review_decision(db, batch_id, "reject", data.get("note") or "Reviewer rejected the harvest candidate after inspection.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 200


@app.route("/api/batch/<batch_id>/stage", methods=["POST"])
def advance_stage(batch_id: str):
    db = get_db()
    row = db.execute("SELECT stage, validation_status, record_hash FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if row["validation_status"] != "APPROVED" or not row["record_hash"]:
        return jsonify({"error": "Batch must be committed before advancing custody stage."}), 409
    target = (request.get_json(silent=True) or {}).get("stage")
    if target not in STAGES:
        return jsonify({"error": f"stage must be one of {STAGES}"}), 400
    current_index = STAGES.index(row["stage"])
    target_index = STAGES.index(target)
    if target_index <= current_index:
        return jsonify({"error": f"batch is already at or past '{target}'"}), 400
    if target_index != current_index + 1:
        return jsonify({"error": f"custody must advance sequentially to '{STAGES[current_index + 1]}'"}), 400
    timestamp = now_iso()
    note = (request.get_json(silent=True) or {}).get("note") or f"Custody advanced to {target}."
    db.execute("UPDATE batches SET stage = ? WHERE batch_id = ?", (target, batch_id))
    add_custody_event(db, batch_id, target, note, timestamp)
    db.commit()
    return jsonify(enrich_batch(db, db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone())), 200


@app.route("/api/verify/<batch_id>", methods=["GET"])
def verify_batch(batch_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if not row["record_hash"]:
        return jsonify({"batch_id": batch_id, "verified": False, "status": row["validation_status"], "reason": "Batch is not committed yet."})
    batch = batch_dict(row)
    recomputed = compute_record_hash(batch, row["prev_hash"])
    live_evidence_hash = compute_evidence_bundle_hash(db, batch_id)
    evidence_verified = bool(row["evidence_hash"]) and evidence_status(db, batch_id) == "COMPLETE" and (live_evidence_hash == row["evidence_hash"])
    chain = verify_chain(db, batch_id)
    custody = verify_custody(db, batch_id, row["record_hash"])
    verified = recomputed == row["record_hash"] and evidence_verified and chain["verified"] and custody["verified"]
    if verified:
        reason = "Hash + evidence bundle + batch chain + custody trail match. Evidence is unchanged since commit."
    elif not evidence_verified:
        reason = "Evidence bundle hash mismatch: a linked evidence file or analysis record changed after commit."
    elif not chain["verified"]:
        reason = chain.get("reason", "Batch chain verification failed.")
    elif not custody["verified"]:
        reason = custody.get("reason", "Custody verification failed.")
    else:
        reason = "Record hash does not match the committed data."
    return jsonify({
        "batch_id": batch_id,
        "verified": verified,
        "stored_hash": row["record_hash"],
        "recomputed_hash": recomputed,
        "stored_evidence_hash": row["evidence_hash"],
        "live_evidence_hash": live_evidence_hash,
        "evidence_verified": evidence_verified,
        "chain_verified": chain["verified"],
        "custody_verified": custody["verified"],
        "broken_at": chain.get("broken_at") or custody.get("broken_at"),
        "reason": reason,
    })


@app.route("/api/batch/<batch_id>/tamper", methods=["POST"])
def tamper_batch(batch_id: str):
    """DEMO ONLY: change an off-chain field without updating the committed hash."""
    if not DEMO_CONTROLS_ENABLED:
        return jsonify({"error": "Demo controls are disabled on this deployment."}), 403
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if not row["record_hash"]:
        return jsonify({"error": "Only committed batches can be tampered with for the demo."}), 409
    data = request.get_json(silent=True) or {}
    field = data.get("field", "quantity_kg")
    allowed = {"quantity_kg", "apiary_name", "beekeeper_name", "region", "floral_source"}
    if field not in allowed:
        return jsonify({"error": "unsupported field"}), 400
    if field == "quantity_kg":
        value = float(data.get("value", float(row["quantity_kg"]) + 5.0))
    else:
        value = data.get("value") or "TAMPERED VALUE"
    db.execute(f"UPDATE batches SET {field} = ? WHERE batch_id = ?", (value, batch_id))
    db.commit()
    return jsonify({"message": f"Demo tampering applied to {field}; committed hash was not changed.", "batch_id": batch_id}), 200


# ---------------------------------------------------------------------------
# Image analysis (supplementary)
# ---------------------------------------------------------------------------

@app.route("/api/batch/<batch_id>/evidence", methods=["POST"])
def upload_evidence(batch_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if row["record_hash"]:
        return jsonify({"error": "Committed evidence is immutable in the prototype. Add new evidence in a future versioned record."}), 409
    if row["validation_status"] == "REJECTED":
        return jsonify({"error": "Rejected batches cannot be modified."}), 409
    batch_dir = evidence_dir(batch_id)
    added = []
    for kind, field in (("pre_harvest", "pre_image"), ("post_harvest", "post_image"), ("health_screen", "health_image")):
        file = request.files.get(field)
        if not file or not file.filename:
            continue
        ext = Path(file.filename).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            return jsonify({"error": f"Unsupported image type for {field}"}), 400
        try:
            probe = Image.open(file.stream)
            probe.verify()
            file.stream.seek(0)
        except Exception:
            return jsonify({"error": f"Invalid or unreadable image for {field}"}), 400
        dest = batch_dir / f"{kind}{ext}"
        file.save(dest)
        analysis = None
        if kind == "health_screen":
            analysis = predict_disease_risk_from_image(str(dest))
            analysis["label"] = "Varroa-associated visual risk screening (supplementary)"
        db.execute("DELETE FROM harvest_evidence WHERE batch_id=? AND evidence_type=?", (batch_id, kind))
        added.append(add_evidence_record(db, batch_id, kind, dest, source="uploaded-camera", analysis=analysis,
                                         note="Uploaded camera evidence; visual screening is supplementary and not a diagnosis." if analysis else "Uploaded harvest image evidence."))
        if analysis:
            db.execute("UPDATE batches SET image_risk=?, image_score=?, image_method=?, health_warning=? WHERE batch_id=?",
                       (analysis.get("risk"), analysis.get("score"), analysis.get("method"),
                        f"Visual screening: {analysis.get('risk')} risk; beekeeper/expert confirmation remains required.", batch_id))
    db.execute("UPDATE batches SET evidence_status=? WHERE batch_id=?", (evidence_status(db, batch_id), batch_id))
    db.commit()
    return jsonify({"batch_id": batch_id, "added": added, "evidence_status": evidence_status(db, batch_id), "evidence": list_evidence(db, batch_id)}), 200


@app.route("/api/batch/<batch_id>/analyze-image", methods=["POST"])
def analyze_image(batch_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if row["validation_status"] == "REJECTED":
        return jsonify({"error": "Rejected batches cannot be modified."}), 409
    if "image" not in request.files:
        return jsonify({"error": "no image uploaded"}), 400
    image = request.files["image"]
    if not image.filename:
        return jsonify({"error": "empty filename"}), 400
    batch_dir = evidence_dir(batch_id)
    path = batch_dir / f"health_screen_{int(datetime.now(timezone.utc).timestamp())}.png"
    image.save(path)
    try:
        result = predict_disease_risk_from_image(str(path))
        result["label"] = "Varroa-associated visual risk screening (supplementary)"
    except Exception as exc:
        return jsonify({"error": f"image analysis failed: {exc}"}), 500
    if row["record_hash"]:
        return jsonify({"batch_id": batch_id, "image_analysis": result, "note": "Committed record is immutable; this analysis is advisory only and is not added to the committed evidence bundle."}), 200
    db.execute("DELETE FROM harvest_evidence WHERE batch_id=? AND evidence_type='health_screen'", (batch_id,))
    add_evidence_record(db, batch_id, "health_screen", path, source="uploaded-camera", analysis=result,
                        note="Supplementary visual screening; not a diagnosis.")
    db.execute("UPDATE batches SET image_risk=?, image_score=?, image_method=?, health_warning=?, evidence_status=? WHERE batch_id=?",
               (result["risk"], result["score"], result["method"],
                f"Visual screening: {result['risk']} risk; inspect hive and confirm suspected conditions with an expert/lab.", evidence_status(db, batch_id), batch_id))
    if result["risk"] in {"medium", "high"}:
        record_health_alert(db, row["hive_id"], result["risk"], "VISUAL_SCREEN", "Visual screening raised a possible Varroa-associated risk signal; inspect hive.", "camera-ai", now_iso())
    db.commit()
    return jsonify({"batch_id": batch_id, "image_analysis": result, "evidence": list_evidence(db, batch_id)}), 200


@app.route("/api/batch/<batch_id>/demo-health-screen", methods=["POST"])
def demo_health_screen(batch_id: str):
    if not DEMO_CONTROLS_ENABLED:
        return jsonify({"error": "Demo controls are disabled on this deployment."}), 403
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
    if row is None:
        return jsonify({"error": "batch not found"}), 404
    if row["record_hash"]:
        return jsonify({"error": "Committed evidence is immutable; use /analyze-image for advisory-only screening."}), 409
    if row["validation_status"] == "REJECTED":
        return jsonify({"error": "Rejected batches cannot be modified."}), 409
    risk = row["ai_disease_risk"] or "low"
    path = evidence_dir(batch_id) / "health_screen_demo.png"
    generate_demo_health_image(batch_id, risk, path)
    result = predict_disease_risk_from_image(str(path))
    result["label"] = "Varroa-associated visual risk screening (demo signal)"
    db.execute("DELETE FROM harvest_evidence WHERE batch_id=? AND evidence_type='health_screen'", (batch_id,))
    add_evidence_record(db, batch_id, "health_screen", path, source="synthetic-demo", analysis=result,
                        note="Synthetic visual screen for demonstration only; not a diagnosis.")
    db.execute("UPDATE batches SET image_risk=?, image_score=?, image_method=?, health_warning=?, evidence_status=? WHERE batch_id=?",
               (result["risk"], result["score"], result["method"],
                f"Visual screening: {result['risk']} risk; expert/lab confirmation required for any suspected disease or parasite.", evidence_status(db, batch_id), batch_id))
    if result["risk"] in {"medium", "high"}:
        record_health_alert(db, row["hive_id"], result["risk"], "VISUAL_SCREEN", "Demo visual screening raised a possible Varroa-associated risk signal.", "synthetic-demo-ai", now_iso())
    db.commit()
    return jsonify({"batch_id": batch_id, "image_analysis": result, "evidence": list_evidence(db, batch_id)}), 200


@app.route("/api/health-alerts", methods=["GET"])
def api_health_alerts():
    db = get_db()
    rows = db.execute(
        "SELECT h.*, v.beekeeper_name, v.apiary_name, v.region FROM health_alerts h "
        "JOIN hives v ON v.hive_id = h.hive_id ORDER BY h.id DESC LIMIT 20"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/hive/<hive_id>/health", methods=["GET"])
def api_hive_health(hive_id: str):
    db = get_db()
    hive = db.execute("SELECT * FROM hives WHERE hive_id=?", (hive_id,)).fetchone()
    if hive is None:
        return jsonify({"error": "hive not found"}), 404
    return jsonify({"hive": dict(hive), "health": health_summary(db, hive), "alerts": [dict(r) for r in db.execute("SELECT * FROM health_alerts WHERE hive_id=? ORDER BY id DESC LIMIT 10", (hive_id,)).fetchall()]})


# ---------------------------------------------------------------------------
# System summary


@app.route("/api/summary", methods=["GET"])
def api_summary():
    db = get_db()
    total_batches = db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
    committed = db.execute("SELECT COUNT(*) FROM batches WHERE record_hash <> ''").fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM batches WHERE validation_status='PENDING_REVIEW'").fetchone()[0]
    rejected = db.execute("SELECT COUNT(*) FROM batches WHERE validation_status='REJECTED'").fetchone()[0]
    readings = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    alerts = db.execute("SELECT COUNT(*) FROM health_alerts WHERE acknowledged=0").fetchone()[0]
    chain = verify_chain(db) if committed else {"verified": True, "reason": "No committed batches yet."}
    return jsonify({
        "version": PROTOTYPE_VERSION, "hives": db.execute("SELECT COUNT(*) FROM hives").fetchone()[0],
        "batches": total_batches, "committed": committed, "pending_review": pending, "rejected": rejected,
        "readings": readings, "active_alerts": alerts, "chain_verified": bool(chain["verified"]),
    })


# ---------------------------------------------------------------------------
# QR / pages
# ---------------------------------------------------------------------------




def current_base_url() -> str:
    if DEMO_BASE_URL:
        return DEMO_BASE_URL
    if has_request_context():
        return request.host_url.rstrip("/")
    return "http://127.0.0.1:5000"

def generate_qr_for_batch(batch_id: str, base_url: str | None = None) -> Path:
    QR_DIR.mkdir(parents=True, exist_ok=True)
    base = (base_url or current_base_url()).rstrip("/")
    scan_url = f"{base}/scan/{batch_id}"
    img = qrcode.make(scan_url)
    path = QR_DIR / f"{batch_id}.png"
    img.save(path)
    return path


@app.route("/qr/<batch_id>")
def get_qr(batch_id: str):
    db = get_db()
    row = db.execute("SELECT record_hash FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None or not row["record_hash"]:
        abort(404)
    path = QR_DIR / f"{batch_id}.png"
    generate_qr_for_batch(batch_id, base_url=current_base_url())
    return send_from_directory(QR_DIR, path.name)


@app.route("/")
def dashboard():
    return render_template("dashboard.html", stages=STAGES, harvest_drop_kg=HARVEST_DROP_KG)


@app.route("/scan/<batch_id>")
def scan_page(batch_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        return render_template("not_found.html", batch_id=batch_id), 404
    batch = enrich_batch(db, row)
    verification = None
    if row["record_hash"]:
        verification = {
            "verified": compute_record_hash(batch, row["prev_hash"]) == row["record_hash"] and row["evidence_hash"] and evidence_status(db, batch_id) == "COMPLETE" and row["evidence_hash"] == compute_evidence_bundle_hash(db, batch_id) and batch["chain_verified"] and batch["custody_verified"],
            "chain_verified": batch["chain_verified"],
            "custody_verified": batch["custody_verified"],
            "evidence_verified": bool(row["evidence_hash"]) and evidence_status(db, batch_id) == "COMPLETE" and row["evidence_hash"] == compute_evidence_bundle_hash(db, batch_id),
        }
    return render_template("scan.html", batch=batch, verification=verification)


@app.cli.command("init-db")
def cli_init_db():
    init_db()
    print(f"Database initialized at {DB_PATH}")


# Ensure an import-based deployment/test run has a valid schema too.
# init_db() is idempotent and also performs legacy migrations.
init_db()

if __name__ == "__main__":
    app.run(debug=False, port=5000, host="0.0.0.0", use_reloader=False)
