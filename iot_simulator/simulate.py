"""IoT hive simulator for Nectar Chain / SIH 26021.

Models the upgraded architecture:
    hive sensors -> /iot/reading -> harvest detection -> AI health/yield validation

The simulator stands in for ESP32 + gateway traffic. It does NOT bypass the
backend harvest detector or ledger commit logic.
"""
from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime, timezone
import requests

BACKEND_URL = "http://127.0.0.1:5000"
POLL_SECONDS = 4
DEMO_HARVEST_HIVE = "HIVE-001"
HARVEST_INTERVAL = 8
_state = {}


def h_offset(hive_id: str) -> int:
    return int(hashlib.md5(hive_id.encode()).hexdigest()[:4], 16)


def get_hives():
    r = requests.get(f"{BACKEND_URL}/api/hives", timeout=5)
    r.raise_for_status()
    return r.json()


def reading_for(hive: dict) -> dict:
    hive_id = hive["hive_id"]
    offset = h_offset(hive_id)
    state = _state.setdefault(hive_id, {"weight": float(hive.get("last_weight") or 31 + offset % 7), "ticks": 0})
    state["ticks"] += 1

    temperature = 34.2 + ((offset % 7) - 3) * 0.25 + random.uniform(-0.35, 0.35)
    humidity = 54.0 + ((offset % 5) - 2) * 1.0 + random.uniform(-2.0, 2.0)
    state["weight"] += random.uniform(-0.03, 0.04)

    if hive_id == DEMO_HARVEST_HIVE and state["ticks"] % HARVEST_INTERVAL == 0:
        state["weight"] -= 6.0
        print(f"\n>>> DEMO HARVEST EVENT: {hive_id} weight dropped ~6 kg <<<\n")

    return {
        "hive_id": hive_id,
        "temperature": round(temperature, 2),
        "humidity": round(humidity, 2),
        "weight": round(max(5, state["weight"]), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo_mode": hive_id == DEMO_HARVEST_HIVE,
    }


def send(reading: dict):
    r = requests.post(f"{BACKEND_URL}/iot/reading", json=reading, timeout=5)
    r.raise_for_status()
    body = r.json()
    event = body.get("harvest_event")
    line = (f"{reading['timestamp']} | {reading['hive_id']} | "
            f"T={reading['temperature']}C H={reading['humidity']}% W={reading['weight']}kg")
    print(line)
    health_risk = body.get("reading", {}).get("health_risk")
    if health_risk in {"medium", "high"}:
        print(f"  HEALTH WARNING -> {health_risk.upper()} risk; inspect hive / collect visual evidence")
    if event:
        print(f"  HARVEST -> {event['batch_id']} | {event['validation_status']} | {event['reason']}")
        if event.get("committed"):
            print(f"  COMMITTED -> QR ready: {event.get('qr_url')}")
        else:
            print("  MANUAL REVIEW REQUIRED -> not committed, no QR generated")


def main():
    print("Nectar Chain IoT simulator starting...")
    print(f"Backend: {BACKEND_URL}")
    print(f"Demo harvest hive: {DEMO_HARVEST_HIVE}")
    while True:
        try:
            hives = get_hives()
            if not hives:
                print("No registered hives. Run seed_demo.py or register a hive.")
            for hive in hives:
                try:
                    send(reading_for(hive))
                except requests.RequestException as exc:
                    print(f"  [send error] {exc}")
            time.sleep(POLL_SECONDS)
        except requests.RequestException as exc:
            print(f"[backend error] {exc}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
