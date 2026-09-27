"""
Provar försiktigt bildinställningar (exponeringsläge, motljus/WDR,
3D-brusreducering) på trafikkameran för att hitta en bättre bild över
tid, utan att riskera att lämna kameran i ett trasigt läge.

Bakgrund: ett manuellt test av exponeringsläget "Anti-Smearing" (tänkt
att minska rörelseoskärpa nattetid) gav en kraftigt överexponerad bild -
IR-ljuset studsade mot närliggande buskage och brände ut halva bilden.
Skärpemåttet ensamt (Laplacian-varians i vägregionen) missade detta
helt, eftersom det bara tittar på ett litet utsnitt. Därför:

1. Aldrig mer än EN inställning testas per körning.
2. En hälsokontroll (andel över-/underexponerade pixlar över HELA
   bilden, se reolink_client.exposure_health) måste godkännas INNAN
   skärpan ens utvärderas. Underkänd hälsa -> omedelbar återställning.
3. Varje resultat (behållet/återställt/svartlistat) sparas permanent i
   STATE_PATH, så samma riskabla experiment aldrig upprepas blint.

Körs mer sällan än camera_focus.py (var 6:e timme) eftersom det här är
strukturella lägesbyten, inte kontinuerlig finjustering.
"""

import json
import os
import time
from datetime import datetime

from src.ccounter.config import FOCUS_REGION
from src.ccounter.reolink_client import (
    exposure_health,
    get_isp,
    get_snapshot,
    is_ir_mode,
    login,
    logout,
    noise_score,
    set_isp,
    sharpness_score,
)

STATE_PATH = "data/camera_isp_state.json"
LOG_PATH = "data/camera_isp_tuning.log"

SETTLE_SECONDS = 4  # ge autoexponeringen tid att stabilisera innan mätning
MIN_SCORE_RATIO_TO_KEEP = 0.97  # tillåt att behålla vid i princip oförändrad skärpa
MAX_NOISE_RATIO = 3.0  # nr3d=0 gav ~18x - detta ger bred marginal ändå

# (isp-fält, nytt värde, vilket ljusläge det får testas i: "day"/"night"/"both")
# Ordning = testprioritet. exposure=Manual utelämnat med avsikt (kräver att
# shutter+gain tunas ihop, för stor risk för ett enkelt on/off-test).
CANDIDATES: list[tuple[str, object, str]] = [
    ("backLight", "DynamicRangeControl", "both"),
    ("backLight", "BackLightControl", "both"),
    ("exposure", "LowNoise", "both"),
    ("nr3d", 0, "both"),
]

# Redan känt från manuellt test 2026-09-27 (se konversationshistorik) -
# förifyllt så det aldrig provas om automatiskt.
_SEED_TRIALS = {
    "exposure=Anti-Smearing:night": {
        "outcome": "unsafe_reverted",
        "note": (
            "Manuellt testat 2026-09-27: ~höger tredjedel av bilden helt "
            "överexponerad (IR mot närliggande häck). Återställt till Auto."
        ),
        "timestamp": "2026-09-27T20:55:31",
    },
    "nr3d=0:night": {
        "outcome": "unsafe_reverted",
        "note": (
            "Manuellt testat 2026-09-27: extremt korngrynig bild (brus ~18x "
            "normalt). sharpness_score gav falskt 100x 'förbättring' eftersom "
            "Laplacian-variansen inte skiljer på brus och riktig skärpa - "
            "därför lades noise_score till som extra spärr. Återställt till 1."
        ),
        "timestamp": "2026-09-27T21:04:44",
    },
}


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
    else:
        state = {"trials": {}}

    for key, value in _SEED_TRIALS.items():
        state["trials"].setdefault(key, value)

    return state


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def pick_next_candidate(state: dict, mode: str):
    for field, value, applicable_mode in CANDIDATES:
        if applicable_mode not in ("both", mode):
            continue
        key = f"{field}={value}:{mode}"
        if key in state["trials"]:
            continue
        return field, value, key
    return None


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
    state = load_state()

    try:
        img = get_snapshot(token)
    except Exception as exc:
        log(f"Kunde inte nå kameran: {exc}")
        return

    if img is None:
        log("Snapshot gick inte att avkoda, avbryter.")
        return

    mode = "night" if is_ir_mode(img) else "day"
    _, baseline_note = exposure_health(img)
    baseline_score = sharpness_score(img, FOCUS_REGION)
    baseline_noise = noise_score(img, FOCUS_REGION)

    log(
        f"Läge={mode} baslinje: skärpa={baseline_score:.0f} brus={baseline_noise:.2f} "
        f"hälsa={baseline_note}"
    )

    candidate = pick_next_candidate(state, mode)
    if candidate is None:
        log("Inga fler otestade inställningar för det här ljusläget just nu.")
        return

    field, value, key = candidate

    try:
        current_isp = get_isp(token)
    except Exception as exc:
        log(f"Kunde inte läsa nuvarande ISP-inställningar: {exc}")
        return

    previous_value = current_isp.get(field)

    if previous_value == value:
        log(f"{field} är redan {value}, inget att testa.")
        state["trials"][key] = {
            "outcome": "already_set",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        save_state(state)
        return

    log(f"Provar {field}={value} (var: {previous_value}) i läge={mode}...")

    if not set_isp(token, {field: value}):
        log(f"  Kunde inte sätta {field}={value}, hoppar över.")
        state["trials"][key] = {
            "outcome": "failed_to_set",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        save_state(state)
        return

    time.sleep(SETTLE_SECONDS)

    try:
        new_img = get_snapshot(token)
    except Exception as exc:
        log(f"  Kunde inte hämta ny snapshot ({exc}) - återställer i säkerhetssyfte.")
        set_isp(token, {field: previous_value})
        state["trials"][key] = {
            "outcome": "error_reverted",
            "note": str(exc),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        save_state(state)
        return

    healthy, note = exposure_health(new_img)

    if not healthy:
        set_isp(token, {field: previous_value})
        log(f"  OSÄKER BILD ({note}) - återställer till {field}={previous_value} och svartlistar.")
        state["trials"][key] = {
            "outcome": "unsafe_reverted",
            "note": note,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        save_state(state)
        return

    new_noise = noise_score(new_img, FOCUS_REGION)
    if new_noise > baseline_noise * MAX_NOISE_RATIO:
        set_isp(token, {field: previous_value})
        note = f"brus {baseline_noise:.2f} -> {new_noise:.2f}"
        log(f"  FÖR BRUSIGT ({note}) - återställer till {field}={previous_value} och svartlistar.")
        state["trials"][key] = {
            "outcome": "unsafe_reverted",
            "note": note,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        save_state(state)
        return

    new_score = sharpness_score(new_img, FOCUS_REGION)
    log(
        f"  Hälsa OK ({note}), brus {baseline_noise:.2f} -> {new_noise:.2f}. "
        f"Skärpa {baseline_score:.0f} -> {new_score:.0f}"
    )

    if new_score >= baseline_score * MIN_SCORE_RATIO_TO_KEEP:
        log(f"  Behåller {field}={value}.")
        state["trials"][key] = {
            "outcome": "kept",
            "baseline_score": baseline_score,
            "new_score": new_score,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        set_isp(token, {field: previous_value})
        log(f"  Sämre skärpa ({new_score:.0f} < {baseline_score:.0f}), återställer till {field}={previous_value}.")
        state["trials"][key] = {
            "outcome": "reverted_worse_sharpness",
            "baseline_score": baseline_score,
            "new_score": new_score,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)


if __name__ == "__main__":
    run()
