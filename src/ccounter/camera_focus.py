"""
Håller kamerans fokus inställt på vägytan vid räknelinjen, automatiskt.

Bakgrund: kameran (Reolink RLC-811A) har motoriserad zoom/fokus och har
observerats låsa autofokus på fel avstånd (t.ex. objekt nära kameran)
istället för vägen där fordonen faktiskt räknas/fotograferas. Det går
inte att fixa i efterhand i bilder som redan tagits - därför körs detta
proaktivt med jämna mellanrum via cron.

Metod: en enkel, försiktig "coordinate search" - prova några steg åt
varje håll från nuvarande fokusläge, mät skärpan (samma Laplacian-
varians-mått som redan används för ANPR-skärpekontroll i app.py/
track_plate_manager.py) i vägregionen kring main_count_line, och behåll
bästa läget. Rör sig aldrig långt per körning och backar till
ursprungsläget om inget bättre hittas.

Nattläge (IR, gråskalebild) hoppas alltid över - fokusoptik för IR
skiljer sig fysiskt från dagsljus och går inte att utvärdera meningsfullt
med samma metod, plus att kameran redan gör sin egen IR-cut-omkoppling.
Körs ändå (som ren avläsning/loggning) så trenden syns över dygnet.
"""

import json
import os
import ssl
import time
import urllib.request
from datetime import datetime

import cv2
import numpy as np

from src.ccounter.config import (
    CAM_PSWD,
    CAM_URL,
    CAM_USER,
    FOCUS_REGION,
    PLATE_READER_SHARPNESS_THRESHOLD,
)

STATE_PATH = "data/camera_focus_state.jsonl"
LOG_PATH = "data/camera_focus.log"

FOCUS_STEP = 15
MAX_STEPS_PER_DIRECTION = 4
MIN_IMPROVEMENT_RATIO = 1.05  # kräv minst 5% bättre skärpa innan fokus flyttas
SETTLE_SECONDS = 1.5

_SSL_CTX = ssl._create_unverified_context()


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def _api_url(cmd: str) -> str:
    return f"{CAM_URL}/cgi-bin/api.cgi?cmd={cmd}"


def _get(cmd: str, token: str | None = None) -> dict:
    url = _api_url(cmd)
    if token:
        url += f"&token={token}"
    with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def _post(cmd: str, payload: list, token: str | None = None) -> dict:
    url = _api_url(cmd)
    if token:
        url += f"&token={token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def login() -> str:
    result = _post(
        "Login",
        [
            {
                "cmd": "Login",
                "action": 0,
                "param": {"User": {"userName": CAM_USER, "password": CAM_PSWD}},
            }
        ],
    )
    return result[0]["value"]["Token"]["name"]


def get_zoom_focus(token: str) -> dict:
    result = _get("GetZoomFocus", token)
    return result[0]["value"]["ZoomFocus"]


def set_focus_pos(token: str, pos: int) -> bool:
    result = _post(
        "StartZoomFocus",
        [
            {
                "cmd": "StartZoomFocus",
                "action": 0,
                "param": {"ZoomFocus": {"channel": 0, "op": "FocusPos", "pos": pos}},
            }
        ],
        token,
    )
    return result[0].get("code") == 0


def get_snapshot(token: str):
    url = _api_url("Snap") + f"&channel=0&rs={int(time.time() * 1000)}&token={token}"
    with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
        data = resp.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def is_ir_mode(img) -> bool:
    b, g, r = (channel.astype(np.int16) for channel in cv2.split(img))
    diff = float(np.mean(np.abs(b - g)) + np.mean(np.abs(g - r)) + np.mean(np.abs(b - r)))
    return diff < 6.0


def sharpness_score(img, region: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = region
    h, w = img.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    crop = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def save_state(entry: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run() -> None:
    if not CAM_URL or not CAM_USER:
        log("CAM/CAM_USER/CAM_PSWD saknas i .env - avbryter.")
        return

    try:
        token = login()
        img = get_snapshot(token)
    except Exception as exc:
        log(f"Kunde inte nå kameran: {exc}")
        return

    if img is None:
        log("Snapshot gick inte att avkoda, avbryter.")
        return

    baseline_score = sharpness_score(img, FOCUS_REGION)

    if is_ir_mode(img):
        log(
            f"IR/nattläge - hoppar över fokusjustering "
            f"(skärpa just nu i vägregionen: {baseline_score:.0f})."
        )
        return

    zf = get_zoom_focus(token)
    start_pos = zf["focus"]["pos"]
    zoom_pos = zf["zoom"]["pos"]

    log(
        f"Start: fokus={start_pos} zoom={zoom_pos} "
        f"skärpa={baseline_score:.0f} (referens för läsbar skylt: "
        f"{PLATE_READER_SHARPNESS_THRESHOLD:.0f})"
    )

    best_pos = start_pos
    best_score = baseline_score

    for direction in (1, -1):
        pos = start_pos
        for step in range(1, MAX_STEPS_PER_DIRECTION + 1):
            pos = start_pos + direction * FOCUS_STEP * step
            try:
                if not set_focus_pos(token, pos):
                    log(f"  Kunde inte sätta fokus till {pos}, avbryter riktning.")
                    break
                time.sleep(SETTLE_SECONDS)
                probe_img = get_snapshot(token)
                score = sharpness_score(probe_img, FOCUS_REGION)
            except Exception as exc:
                log(f"  Fel vid fokus={pos}: {exc}, avbryter riktning.")
                break

            log(f"  riktning={direction:+d} steg={step} fokus={pos} skärpa={score:.0f}")

            if score > best_score:
                best_score = score
                best_pos = pos
            else:
                break

    if best_pos != start_pos and best_score >= baseline_score * MIN_IMPROVEMENT_RATIO:
        set_focus_pos(token, best_pos)
        log(
            f"Klart. Flyttade fokus {start_pos} -> {best_pos} "
            f"(skärpa {baseline_score:.0f} -> {best_score:.0f})."
        )
        result_pos = best_pos
        result_score = best_score
    else:
        set_focus_pos(token, start_pos)
        log(
            f"Ingen tillräcklig förbättring (bäst hittad: {best_pos}={best_score:.0f}). "
            f"Behåller {start_pos}."
        )
        result_pos = start_pos
        result_score = baseline_score

    save_state(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "start_pos": start_pos,
            "result_pos": result_pos,
            "baseline_score": baseline_score,
            "result_score": result_score,
        }
    )


if __name__ == "__main__":
    run()
