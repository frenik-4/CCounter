"""
Bevakar trafikkamerans bildskärpa under dagtid och larmar (pushnotis via
Home Assistant, notify.pixel_9) om den försämras under en tröskel under
en sammanhängande period.

Bakgrund: upptäckte 2026-09-28 (efter att användaren rapporterade att
kvällens bilder var mycket sämre) att kameran periodvis - av ännu oklar
anledning, trots att den egna kontinuerliga autofokusen bekräftat är
avstängd (se camera_focus.py:s docstring för hela felsökningen) -
tappar skärpa kraftigt i TIMMAR i sträck mitt på dagen. Uppmätt konkret
samma dag: skärpa 400-800 under en god period (16:46-17:54), sedan ner
till 40-165 från kl 18 och framåt, utan att fokus eller ISP-inställningar
ändrats. En kameraomstart gjordes som första åtgärd, men om mönstret
återkommer behövs den här bevakningen för att upptäcka det automatiskt
istället för att någon råkar märka det manuellt.

Kräver TVÅ försämrade mätningar i rad (~30 min mellanrum, samma
adaptiva measure_sharpness() som övriga scripts) innan larm skickas -
en enstaka dålig mätning kan vara brus, se lärdomarna i
camera_focus.py. Larmar bara en gång per försämringsperiod (återställs
när skärpan är bra igen).

Körs ofta (var 15:e minut) via cron - hoppar bara över larmlogiken
nattetid (IR-läge har en annan, redan känd baslinje), men loggar ändå
skärpan då för att kunna följa trenden över dygnet.
"""

import json
import os
import urllib.request
from datetime import datetime

from src.ccounter.config import FOCUS_REGION, HA_TOKEN, HA_URL
from src.ccounter.reolink_client import (
    ensure_autofocus_disabled,
    get_snapshot,
    is_ir_mode,
    login,
    logout,
    measure_sharpness,
)

STATE_PATH = "data/camera_quality_state.json"
LOG_PATH = "data/camera_quality_watch.log"

# Bra dagsmätningar har legat på 400-800+, dåliga episoder på 30-165
# (se docstring ovan) - 150 ligger tryggt mellan de intervallen.
SHARPNESS_ALERT_THRESHOLD = 150.0
CONSECUTIVE_BAD_TO_ALERT = 2


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
    return {"consecutive_bad": 0, "alerted": False}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def send_notification(message: str) -> None:
    if not HA_URL or not HA_TOKEN:
        log("  (Kunde inte skicka notis - HA_URL/HA_TOKEN saknas i .env)")
        return

    try:
        url = f"{HA_URL}/api/services/notify/send_message"
        req = urllib.request.Request(
            url,
            data=json.dumps({"entity_id": "notify.pixel_9", "message": message}).encode(),
            headers={
                "Authorization": f"Bearer {HA_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        log("  Notis skickad via notify.pixel_9.")
    except Exception as exc:
        log(f"  Kunde inte skicka notis: {exc}")


def run() -> None:
    try:
        token = login()
    except Exception as exc:
        log(f"Kunde inte nå kameran: {exc}")
        return

    try:
        _run_with_token(token)
    finally:
        logout(token)


def _run_with_token(token: str) -> None:
    try:
        img = get_snapshot(token)
    except Exception as exc:
        log(f"Kunde inte nå kameran: {exc}")
        return

    if img is None:
        log("Snapshot gick inte att avkoda, avbryter.")
        return

    if is_ir_mode(img):
        night_score = measure_sharpness(token, FOCUS_REGION)
        log(f"IR/nattläge - skärpa={night_score:.0f} (ingen larmbevakning nattetid).")
        return

    af_note = ""
    if not ensure_autofocus_disabled(token):
        af_note = " [OBS: kunde inte bekräfta att autofokus är avstängd!]"
        log(f"Kunde inte bekräfta att autofokus är avstängd{af_note}")

    score = measure_sharpness(token, FOCUS_REGION)
    state = load_state()

    if score < SHARPNESS_ALERT_THRESHOLD:
        state["consecutive_bad"] = state.get("consecutive_bad", 0) + 1
        log(
            f"Skärpa={score:.0f} (under tröskel {SHARPNESS_ALERT_THRESHOLD:.0f}), "
            f"{state['consecutive_bad']} mätning(ar) i rad.{af_note}"
        )

        if state["consecutive_bad"] >= CONSECUTIVE_BAD_TO_ALERT and not state.get("alerted"):
            message = (
                f"CCounter: trafikkamerans bild har varit dålig i minst "
                f"{CONSECUTIVE_BAD_TO_ALERT} mätningar i rad (senast skärpa "
                f"{score:.0f}, tröskel {SHARPNESS_ALERT_THRESHOLD:.0f}).{af_note}"
            )
            log(f"  LARM: {message}")
            send_notification(message)
            state["alerted"] = True
    else:
        if state.get("alerted"):
            log(f"Skärpa={score:.0f} - återhämtad, återställer larmstatus.")
        else:
            log(f"Skärpa={score:.0f} (OK).")
        state["consecutive_bad"] = 0
        state["alerted"] = False

    save_state(state)


if __name__ == "__main__":
    run()
