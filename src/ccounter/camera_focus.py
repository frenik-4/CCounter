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

Lärdomar från en lång felsökning 2026-09-28:

1. GRUNDORSAKEN till nästan allt konstigt beteende denna dag: kamerans
   EGNA kontinuerliga autofokus (AutoFocus.disable=0) var påslagen hela
   tiden och kämpade emot varje manuellt FocusPos-kommando - bekräftat
   genom att samma nominella fokusläge flimrade mellan skärpa ~13 och
   ~665 inom loppet av mindre än en sekund (tre foton, 0.4s isär).
   ensure_autofocus_disabled() i reolink_client.py måste lyckas innan
   någon skärpemätning går att lita på - annars avbryts körningen.
2. Sekundär effekt (kvarstår även med AF avstängd): skärpezonen vid
   vägens avstånd är ganska smal i fokusenheter, så ett för stort
   FOCUS_STEP kan hoppa förbi den. Mindre steg + flera prover per
   mätpunkt (behåll bästa) ger en säkrare sökning.
3. Snabb multi-positions-vandring (många fokusflyttar i tät följd) kan
   ge missvisande resultat pga motorbacklash/otillräcklig vila - en
   ren, isolerad mätning (flytta en gång, vila, mät om) är
   tillförlitligare än en snabb sweep över många lägen.

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
    ensure_autofocus_disabled,
    get_snapshot,
    get_zoom_focus,
    is_ir_mode,
    login,
    logout,
    measure_sharpness,
    set_focus_pos,
    sharpness_score,
)

STATE_PATH = "data/camera_focus_state.jsonl"
LOG_PATH = "data/camera_focus.log"

FOCUS_STEP = 5
MAX_STEPS_PER_DIRECTION = 3
MIN_IMPROVEMENT_RATIO = 1.05  # kräv minst 5% bättre skärpa innan fokus flyttas
MIN_ABSOLUTE_IMPROVEMENT = 10.0  # skydd mot near-noll-baslinje (t.ex. helt svart bild)
SETTLE_SECONDS = 1.0  # kort initial paus innan measure_sharpness() tar
# över och väntar adaptivt tills mätningen stabiliserat sig (se
# reolink_client.py - en fast väntetid visade sig omöjlig att gissa rätt)

# TILLFÄLLIGT PÅSLAGET (2026-09-28): kameran uppvisar episoder av flera
# sekunders SAMMANHÄNGANDE dålig skärpa vid samma nominella fokusläge
# (inte bara enstaka brusiga bildrutor - även measure_sharpness()s
# stabilitetskontroll kan luras eftersom två dåliga prov i rad ser
# "stabila" ut). Orsaken är inte fullt klarlagd trots avstängd autofokus.
# Tills mönstret är bättre förstått: kör bara sökningen och LOGGA vad den
# skulle ha gjort, men rör aldrig det faktiska fokusläget - för att inte
# riskera att kameran hamnar i ett sämre läge baserat på en mätning som
# råkar vara mitt i en sådan episod. Sätt till False när grundorsaken är
# hittad och verifierad stabil över flera dagars körning.
DRY_RUN = True


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

    if is_ir_mode(img):
        night_score = sharpness_score(img, FOCUS_REGION)
        log(
            f"IR/nattläge - hoppar över fokusjustering "
            f"(skärpa just nu i vägregionen: {night_score:.0f})."
        )
        return

    if not ensure_autofocus_disabled(token):
        log(
            "Kunde inte bekräfta att kamerans egna autofokus är avstängd - "
            "avbryter (skärpemätningar är annars opålitliga, se lärdomen "
            "i modulens docstring)."
        )
        return

    zf = get_zoom_focus(token)
    start_pos = zf["focus"]["pos"]
    zoom_pos = zf["zoom"]["pos"]

    baseline_score = measure_sharpness(token, FOCUS_REGION)

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
                score = measure_sharpness(token, FOCUS_REGION)
            except Exception as exc:
                log(f"  Fel vid fokus={pos}: {exc}, avbryter riktning.")
                break

            log(f"  riktning={direction:+d} steg={step} fokus={pos} skärpa={score:.0f}")

            if score > best_score:
                best_score = score
                best_pos = pos
            else:
                break

    improved_enough = False

    if best_pos != start_pos:
        # Baslinjen mättes i början av körningen - flera minuter har gått
        # sedan dess (sökningen tar tid), och dis/kondens kan ha ändrats
        # däremellan (uppmätt variation: samma läge gav 511 kl 09:35 och 11
        # kl 09:39 en och samma morgon). En jämförelse mot en gammal
        # baslinje kan därför peka fel håll. Mät om BÅDA lägena nära i tid
        # innan vi committar till en flytt.
        try:
            set_focus_pos(token, start_pos)
            time.sleep(SETTLE_SECONDS)
            recheck_start = measure_sharpness(token, FOCUS_REGION)

            set_focus_pos(token, best_pos)
            time.sleep(SETTLE_SECONDS)
            recheck_best = measure_sharpness(token, FOCUS_REGION)

            log(
                f"  Omkontroll nära i tid: {start_pos}={recheck_start:.0f} "
                f"{best_pos}={recheck_best:.0f}"
            )

            baseline_score, best_score = recheck_start, recheck_best
            improved_enough = (
                recheck_best >= recheck_start * MIN_IMPROVEMENT_RATIO
                and (recheck_best - recheck_start) >= MIN_ABSOLUTE_IMPROVEMENT
            )
        except Exception as exc:
            log(f"  Fel vid omkontroll: {exc}, behåller {start_pos}.")

    try:
        if improved_enough and DRY_RUN:
            set_focus_pos(token, start_pos)
            log(
                f"[DRY RUN] Skulle ha flyttat fokus {start_pos} -> {best_pos} "
                f"(skärpa {baseline_score:.0f} -> {best_score:.0f}), men rör "
                f"inget just nu. Behåller {start_pos}."
            )
            result_pos, result_score = start_pos, baseline_score
        elif improved_enough:
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
