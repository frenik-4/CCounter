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
import time
from datetime import datetime

from src.ccounter.config import FOCUS_REGION, PLATE_READER_SHARPNESS_THRESHOLD
from src.ccounter.reolink_client import (
    get_snapshot,
    get_zoom_focus,
    is_ir_mode,
    login,
    logout,
    set_focus_pos,
    sharpness_score,
)

STATE_PATH = "data/camera_focus_state.jsonl"
LOG_PATH = "data/camera_focus.log"

FOCUS_STEP = 15
MAX_STEPS_PER_DIRECTION = 4
MIN_IMPROVEMENT_RATIO = 1.05  # kräv minst 5% bättre skärpa innan fokus flyttas
MIN_ABSOLUTE_IMPROVEMENT = 10.0  # skydd mot near-noll-baslinje (t.ex. helt svart bild)
SETTLE_SECONDS = 1.5


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def save_state(entry: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


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

    improved_enough = (
        best_pos != start_pos
        and best_score >= baseline_score * MIN_IMPROVEMENT_RATIO
        and (best_score - baseline_score) >= MIN_ABSOLUTE_IMPROVEMENT
    )

    try:
        if improved_enough:
            set_focus_pos(token, best_pos)
            log(
                f"Klart. Flyttade fokus {start_pos} -> {best_pos} "
                f"(skärpa {baseline_score:.0f} -> {best_score:.0f})."
            )
            result_pos, result_score = best_pos, best_score
        else:
            set_focus_pos(token, start_pos)
            log(
                f"Ingen tillräcklig förbättring (bäst hittad: {best_pos}={best_score:.0f}). "
                f"Behåller {start_pos}."
            )
            result_pos, result_score = start_pos, baseline_score
    except Exception as exc:
        log(f"Kunde inte återställa/tillämpa slutligt fokusläge: {exc}")
        result_pos, result_score = None, None

    if result_pos is not None:
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
