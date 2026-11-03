"""
Hälsokontroll för suddig kamerabild. Två lägen, båda läser dagens egna
bilsnapshots från disk (rör inte kamerans API):

  window  Snabb: larmar om bilderna varit suddiga under minst 2 timmar i rad
          dagtid. Kör var 30:e minut (cron, kl 08-17).
  daily   Långsam backup: larmar om dagens median varit suddig 2 dagar i rad.
          Fångar fallet att suddet gör att för få bilar upptäcks för att
          fönsterkontrollen ska kunna bedöma något. Kör en gång per dag.

Bakgrund: 2026-11-01 blev bilden suddig och räkningen föll från ~150 till
~30 fordon per dag, utan att någon märkte det på flera dagar. Normala
dagtidsbilder har skärpa 400-1000 i vägregionen; en suddig dag låg på ~20.

Bara färgbilder bedöms (IR/nattbilder har en annan skärpenivå). I
fönsterläget räknas en bild som suddig om skärpan är under tröskeln, och
larm kräver att minst 80 % av bilderna i de senaste 2 timmarna är suddiga,
att det finns minst 4 bilder som täcker minst 45 minuter (trafiken är gles när
bilden är suddig) - en enda
skarp bild betyder att kameran är igång igen.

Användning:
    python -m src.ccounter.health_check --mode window
    python -m src.ccounter.health_check --mode daily
    python -m src.ccounter.health_check --mode window --now "2026-11-02 13:00" --dry-run
"""

import argparse
import glob
import json
import os
import re
import statistics
import urllib.request
from datetime import datetime, timedelta

import cv2

from src.ccounter.config import FOCUS_REGION, HA_TOKEN, HA_URL, SNAPSHOT_DIR
from src.ccounter.reolink_client import is_ir_mode

STATE_PATH = "data/health_check_state.json"
LOG_PATH = "data/health_check.log"

BLUR_THRESHOLD = 150.0
VEHICLE_CLASSES = ("car", "truck", "bus")

# window-läget
WINDOW = timedelta(hours=2)
WINDOW_MIN_SAMPLES = 4
WINDOW_MIN_SPAN = timedelta(minutes=45)
WINDOW_BLURRY_FRACTION = 0.8

# daily-läget
DAY_HOURS = range(10, 15)
DAILY_MIN_SAMPLES = 5
DAILY_MAX_SAMPLES = 15
CONSECUTIVE_BAD_DAYS_TO_ALERT = 2

_NAME_RE = re.compile(r"/(\d{8})_(\d{6})_event_id")


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
    state.setdefault("daily", {"last_date": None, "consecutive_bad_days": 0, "alerted": False})
    state.setdefault("window", {"alerted": False})
    return state


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def sharpness_if_color(path: str) -> float | None:
    """Skärpa i vägregionen, eller None för oläsliga bilder och IR/nattbilder."""
    img = cv2.imread(path)
    if img is None or is_ir_mode(img):
        return None
    x1, y1, x2, y2 = FOCUS_REGION
    gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def snapshots_for_day(day: str) -> list[tuple[datetime, str]]:
    compact = day.replace("-", "")
    found = []
    for cls in VEHICLE_CLASSES:
        for path in glob.glob(f"{SNAPSHOT_DIR}/{compact}_*_event_id*_{cls}_main_count_line_*.jpg"):
            m = _NAME_RE.search(path)
            if m:
                found.append((datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"), path))
    return sorted(found)


def evenly_spaced(items: list, n: int) -> list:
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


def run_window(now: datetime, dry_run: bool) -> None:
    start = now - WINDOW
    samples = []
    for ts, path in snapshots_for_day(now.strftime("%Y-%m-%d")):
        if start <= ts <= now:
            score = sharpness_if_color(path)
            if score is not None:
                samples.append((ts, score))

    if len(samples) < WINDOW_MIN_SAMPLES:
        log(f"Fönster {start:%H:%M}-{now:%H:%M}: för få färgbilder ({len(samples)} < {WINDOW_MIN_SAMPLES}) - kan inte bedöma.")
        return

    span = samples[-1][0] - samples[0][0]
    blurry = sum(1 for _, s in samples if s < BLUR_THRESHOLD)
    fraction = blurry / len(samples)
    median = statistics.median(s for _, s in samples)
    is_blurry = span >= WINDOW_MIN_SPAN and fraction >= WINDOW_BLURRY_FRACTION
    log(
        f"Fönster {start:%H:%M}-{now:%H:%M}: {len(samples)} bilder över {int(span.total_seconds() // 60)} min, "
        f"{fraction:.0%} suddiga, median {median:.0f} -> {'SUDDIG' if is_blurry else 'ok'}"
    )
    if dry_run:
        return

    state = load_state()
    window = state["window"]
    if is_blurry and not window["alerted"]:
        send_notification(
            f"CCounter: kamerabilden har varit suddig i minst 2 timmar ({fraction:.0%} av {len(samples)} bilder, "
            f"median skärpa {median:.0f}, normalt 400-1000). Räkningen blir för låg - kolla fokus/autofokus i kameran."
        )
        window["alerted"] = True
    elif not is_blurry and window["alerted"] and fraction < 0.5:
        send_notification(f"CCounter: kamerabilden är tillbaka till normal (median skärpa {median:.0f}).")
        window["alerted"] = False
    save_state(state)


def run_daily(day: str, dry_run: bool) -> None:
    candidates = [(ts, p) for ts, p in snapshots_for_day(day) if ts.hour in DAY_HOURS]
    scores = []
    for _, path in evenly_spaced(candidates, DAILY_MAX_SAMPLES):
        score = sharpness_if_color(path)
        if score is not None:
            scores.append(score)

    if len(scores) < DAILY_MIN_SAMPLES:
        log(f"{day}: för få dagtidsbilder ({len(scores)} < {DAILY_MIN_SAMPLES}) - hoppar över, räknare oförändrade.")
        return

    median = statistics.median(scores)
    bad = median < BLUR_THRESHOLD
    log(f"{day}: median skärpa {median:.0f} över {len(scores)} bilder -> {'SUDDIG' if bad else 'ok'}")
    if dry_run:
        return

    state = load_state()
    daily = state["daily"]
    if daily.get("last_date") == day:
        log("  Redan bedömd för det här datumet - ändrar inget.")
        return
    daily["last_date"] = day

    if bad:
        daily["consecutive_bad_days"] += 1
        if daily["consecutive_bad_days"] >= CONSECUTIVE_BAD_DAYS_TO_ALERT and not daily["alerted"]:
            send_notification(
                f"CCounter: kamerabilden har varit suddig {daily['consecutive_bad_days']} dagar i rad "
                f"(median skärpa {median:.0f}, normalt 400-1000). Dagarna kan flaggas som opålitliga i statistiken."
            )
            daily["alerted"] = True
    else:
        if daily["alerted"]:
            send_notification(f"CCounter: dagens kamerabild är normal igen (median skärpa {median:.0f}).")
        daily["consecutive_bad_days"] = 0
        daily["alerted"] = False
    save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["window", "daily"], default="daily")
    parser.add_argument("--now", help='Simulerad nutid "YYYY-MM-DD HH:MM" (för test)')
    parser.add_argument("--dry-run", action="store_true", help="mät och logga, men ändra inget state och skicka inga notiser")
    args = parser.parse_args()
    now = datetime.strptime(args.now, "%Y-%m-%d %H:%M") if args.now else datetime.now()
    if args.mode == "window":
        run_window(now, args.dry_run)
    else:
        run_daily(now.strftime("%Y-%m-%d"), args.dry_run)
