"""
Långsam hälsokontroll: larmar om kamerabilden varit suddig två dagar i rad.

Bakgrund: 2026-11-01 blev bilden suddig och räkningen föll från ~150 till
~30 fordon per dag, utan att någon märkte det på flera dagar. Kontrollen
körs en gång per dag (cron, eftermiddag) och mäter skärpan i vägregionen på
dagens egna bilsnapshots från kl 10-14 - den rör alltså inte kamerans API.

Medianen över dagens snapshots används (inte enskilda bilder): en bil i
rörelse eller en enstaka dålig bildruta ska inte ge falskt larm. Normala
dagar har median 400-1000; en suddig dag låg på ~20. Två dåliga dagar i rad
krävs innan larm, eftersom kameran tidigare haft enstaka dåliga dagar som
läker av sig själva.

Användning:
    python -m src.ccounter.health_check                 # idag
    python -m src.ccounter.health_check --date 2026-11-02 --dry-run
"""

import argparse
import glob
import json
import os
import statistics
import urllib.request
from datetime import date as date_cls
from datetime import datetime

import cv2

from src.ccounter.config import FOCUS_REGION, HA_TOKEN, HA_URL, SNAPSHOT_DIR

STATE_PATH = "data/health_check_state.json"
LOG_PATH = "data/health_check.log"

BLUR_THRESHOLD = 150.0
MIN_SAMPLES = 5
MAX_SAMPLES = 15
CONSECUTIVE_BAD_DAYS_TO_ALERT = 2
DAY_HOURS = range(10, 15)
VEHICLE_CLASSES = ("car", "truck", "bus")


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_date": None, "consecutive_bad_days": 0, "alerted": False}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def sharpness(path: str) -> float | None:
    img = cv2.imread(path)
    if img is None:
        return None
    x1, y1, x2, y2 = FOCUS_REGION
    gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def day_snapshots(day: str) -> list[str]:
    compact = day.replace("-", "")
    files = []
    for hour in DAY_HOURS:
        for cls in VEHICLE_CLASSES:
            files += glob.glob(
                f"{SNAPSHOT_DIR}/{compact}_{hour:02d}*_event_id*_{cls}_main_count_line_*.jpg"
            )
    return sorted(files)


def evenly_spaced(items: list[str], n: int) -> list[str]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def send_notification(message: str) -> None:
    if not HA_URL or not HA_TOKEN:
        log("  Kunde inte skicka notis: HA_URL/HA_TOKEN saknas i .env")
        return
    try:
        req = urllib.request.Request(
            f"{HA_URL}/api/services/notify/send_message",
            data=json.dumps({"entity_id": "notify.pixel_9", "message": message}).encode(),
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        log("  Notis skickad via notify.pixel_9.")
    except Exception as exc:
        log(f"  Kunde inte skicka notis: {exc}")


def run(day: str, dry_run: bool) -> None:
    files = evenly_spaced(day_snapshots(day), MAX_SAMPLES)
    scores = [s for s in (sharpness(f) for f in files) if s is not None]

    if len(scores) < MIN_SAMPLES:
        log(f"{day}: för få dagtidsbilder ({len(scores)} < {MIN_SAMPLES}) - hoppar över, räknare oförändrade.")
        return

    median = statistics.median(scores)
    bad = median < BLUR_THRESHOLD
    log(f"{day}: median skärpa {median:.0f} över {len(scores)} bilder -> {'SUDDIG' if bad else 'ok'}")

    if dry_run:
        return

    state = load_state()
    if state.get("last_date") == day:
        log("  Redan bedömd för det här datumet - ändrar inget.")
        return
    state["last_date"] = day

    if bad:
        state["consecutive_bad_days"] = state.get("consecutive_bad_days", 0) + 1
        if state["consecutive_bad_days"] >= CONSECUTIVE_BAD_DAYS_TO_ALERT and not state.get("alerted"):
            send_notification(
                f"CCounter: kamerabilden har varit suddig {state['consecutive_bad_days']} dagar i rad "
                f"(median skärpa {median:.0f}, normalt 400-1000). Räkningen blir för låg - kolla fokus/"
                f"autofokus i kameran. Dagarna kan flaggas som opålitliga i statistiken."
            )
            state["alerted"] = True
    else:
        if state.get("alerted"):
            send_notification(f"CCounter: kamerabilden är tillbaka till normal (median skärpa {median:.0f}).")
        state["consecutive_bad_days"] = 0
        state["alerted"] = False

    save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--dry-run", action="store_true", help="mät och logga, men ändra inget state och skicka inga notiser")
    args = parser.parse_args()
    run(args.date, args.dry_run)
