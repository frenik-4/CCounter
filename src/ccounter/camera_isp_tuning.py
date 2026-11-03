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
    ensure_autofocus_disabled,
    exposure_health,
    get_isp,
    get_snapshot,
    is_ir_mode,
    login,
    logout,
    measure_sharpness,
    noise_score,
    set_isp,
)

STATE_PATH = "data/camera_isp_state.json"
LOG_PATH = "data/camera_isp_tuning.log"

SETTLE_SECONDS = 4  # ge autoexponeringen tid att stabilisera innan mätning
MIN_SCORE_RATIO_TO_KEEP = 0.97  # tillåt att behålla vid i princip oförändrad skärpa
MAX_NOISE_RATIO = 3.0  # nr3d=0 gav ~18x - detta ger bred marginal ändå
MIN_ABSOLUTE_SCORE_TO_TRUST = 5.0  # under detta är skärpemåttet för brusigt för att lita på

# TILLFÄLLIGT PÅSLAGET (2026-09-28) - se DRY_RUN i camera_focus.py för
# full förklaring: kameran uppvisar episoder av flera sekunders
# sammanhängande dålig skärpa av oklar orsak, vilket kan lura även denna
# moduls skärpejämförelser. Kör bara testet och LOGGA vad utfallet skulle
# blivit, men lämna alltid inställningen som den var innan.
DRY_RUN = True

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

    if not ensure_autofocus_disabled(token):
        log(
            "Kunde inte bekräfta att kamerans egna autofokus är avstängd - "
            "avbryter (skärpemätningar är annars opålitliga)."
        )
        return

    mode = "night" if is_ir_mode(img) else "day"
    _, baseline_note = exposure_health(img)
    baseline_noise = noise_score(img, FOCUS_REGION)
    # Skärpan mäts separat med flera färska prover (se measure_sharpness) -
    # ett enda foto är för brusigt (vind i löv/grenar) för att lita på.
    baseline_score = measure_sharpness(token, FOCUS_REGION)

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

    log(f"  Hälsa OK ({note}), brus {baseline_noise:.2f} -> {new_noise:.2f}.")

    # Den tidiga skärpe-baslinjen (mätt innan set_isp/settle/hälsokontroll)
    # kan vara flera sekunder gammal och missvisande - dis/kondens ändras
    # snabbt (uppmätt: samma läge gav 511 kl 09:35 och 11 kl 09:39 samma
    # morgon). Mät om BÅDA lägena nära i tid istället för att lita på den
    # gamla baslinjen.
    recheck_candidate = measure_sharpness(token, FOCUS_REGION)

    set_isp(token, {field: previous_value})
    time.sleep(SETTLE_SECONDS)
    recheck_previous = measure_sharpness(token, FOCUS_REGION)

    log(
        f"  Omkontroll nära i tid: {field}={value} -> {recheck_candidate:.0f}  "
        f"{field}={previous_value} -> {recheck_previous:.0f}"
    )

    # Vid en väldigt låg baslinje (t.ex. tät dis) är kvotjämförelsen
    # opålitlig - en obetydlig absolut skillnad kan se ut som en stor
    # procentuell förändring åt endera hållet. Lita då bara på
    # hälso-/brusspärrarna ovan istället för skärpekvoten.
    baseline_unreliable = recheck_previous < MIN_ABSOLUTE_SCORE_TO_TRUST

    if baseline_unreliable or recheck_candidate >= recheck_previous * MIN_SCORE_RATIO_TO_KEEP:
        if DRY_RUN:
            # previous_value är redan aktivt (satt ovan för omkontrollen) -
            # rör inget på riktigt, bara logga vad som skulle ha hänt.
            log(f"  [DRY RUN] Skulle ha behållit {field}={value}, men rör inget just nu.")
            outcome = "would_keep_dry_run"
        else:
            set_isp(token, {field: value})
            log(f"  Behåller {field}={value}.")
            outcome = "kept"
        state["trials"][key] = {
            "outcome": outcome,
            "baseline_score": recheck_previous,
            "new_score": recheck_candidate,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        # previous_value är redan aktivt (satt ovan för omkontrollen).
        log(
            f"  Sämre skärpa ({recheck_candidate:.0f} < {recheck_previous:.0f}), "
            f"återställer till {field}={previous_value}."
        )
        state["trials"][key] = {
            "outcome": "reverted_worse_sharpness",
            "baseline_score": recheck_previous,
            "new_score": recheck_candidate,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)


if __name__ == "__main__":
    run()
