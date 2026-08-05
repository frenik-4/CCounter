"""
ANPR-worker — bearbetar sparade snapshots och uppdaterar databasen med regnummer.

Körs fristående, inte i realtid. Fungerar både för nya events (med _anpr.jpg-crop)
och retroaktivt för befintliga events (croppar från annoterad fullbild med bbox).

Användning:
    python -m src.ccounter.anpr_worker
"""

import os
import signal
import sys
import time

import cv2

LOCK_FILE = "/tmp/ccounter_anpr_worker.lock"


def _handle_sigterm(signum, frame) -> None:
    # timeout(1) skickar SIGTERM om körningen tar för lång tid. Utan denna
    # hanterare dör processen direkt utan att köra main()s finally-block,
    # vilket lämnar låsfilen kvar och blockerar nästa timmes körning.
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)

from src.ccounter.config import (
    DATABASE_PATH,
    PLATE_MIN_CONFIDENCE,
    PLATE_READER_GPU,
    PLATE_READER_SHARPNESS_THRESHOLD,
)
from src.ccounter.database import Database
from src.ccounter.plate_reader import PlateReader


def crop_vehicle(image, x1: int, y1: int, x2: int, y2: int):
    """Croppa fordonet ur en annoterad fullbild med bbox-koordinater."""
    fh, fw = image.shape[:2]
    padding_x = int((x2 - x1) * 0.05)
    crop_x1 = max(0, x1 - padding_x)
    crop_x2 = min(fw, x2 + padding_x)
    crop_y1 = max(0, y1)
    crop_y2 = min(fh, y2)

    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
        return None

    return image[crop_y1:crop_y2, crop_x1:crop_x2]


def try_read(plate_reader: PlateReader, image) -> tuple[str, float] | None:
    """Kör OCR på en bild. Returnerar (plate_text, confidence) eller None."""
    result = plate_reader.read_plate_from_image_array(image)

    if not result.get("plate_found"):
        return None

    confidence = float(result["confidence"])

    if confidence < PLATE_MIN_CONFIDENCE:
        return None

    return result["plate_text"], confidence


def process_event(event, plate_reader: PlateReader) -> tuple[str, float] | None:
    """
    Försöker läsa regnummer för ett event.

    1. Provar _anpr1.jpg–_anpr5.jpg (top-5 skarpaste crops), tar högst konfidens.
    2. Bakåtkompatibilitet: _anpr.jpg (gammal namnkonvention utan nummer).
    3. Croppar ur fullbild med bbox (retroaktiv metod).
    4. Hela bilden som sista utväg.
    """
    snapshot_path = event["snapshot_path"]

    if not snapshot_path or not os.path.exists(snapshot_path):
        return None

    # --- Försök 1: numrerade ANPR-crops (top-5, bäst konfidens vinner) ---
    # Avbryter tidigt vid hög konfidens - sparar CPU-tid på CPU-baserad OCR.
    EARLY_EXIT_CONFIDENCE = 0.7
    best_result: tuple[str, float] | None = None
    for i in range(1, 6):
        anpr_path = snapshot_path.replace(".jpg", f"_anpr{i}.jpg")
        if not os.path.exists(anpr_path):
            break
        image = cv2.imread(anpr_path)
        if image is None:
            continue
        result = try_read(plate_reader, image)
        if result is not None and (best_result is None or result[1] > best_result[1]):
            best_result = result
        if best_result is not None and best_result[1] >= EARLY_EXIT_CONFIDENCE:
            break

    if best_result is not None:
        return best_result

    # --- Bakåtkompatibilitet: _anpr.jpg (äldre events utan nummer) ---
    legacy_path = snapshot_path.replace(".jpg", "_anpr.jpg")
    if os.path.exists(legacy_path):
        image = cv2.imread(legacy_path)
        if image is not None:
            result = try_read(plate_reader, image)
            if result is not None:
                return result

    # --- Försök 2: croppa ur fullbild med bbox (retroaktiv) ---
    x1 = event["bbox_x1"]
    y1 = event["bbox_y1"]
    x2 = event["bbox_x2"]
    y2 = event["bbox_y2"]

    full_image = cv2.imread(snapshot_path)
    if full_image is None:
        return None

    if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
        crop = crop_vehicle(full_image, x1, y1, x2, y2)
        if crop is not None:
            result = try_read(plate_reader, crop)
            if result is not None:
                return result

    # --- Försök 3: hela bilden (sista utväg om bbox saknas) ---
    return try_read(plate_reader, full_image)


def main() -> None:
    if os.path.exists(LOCK_FILE):
        print("ANPR-worker körs redan — avslutar.")
        sys.exit(0)

    open(LOCK_FILE, "w").close()
    try:
        _run()
    finally:
        os.remove(LOCK_FILE)


# Antal events per batch innan GPU-cachen rensas. Håller nere
# toppminnesanvändningen istället för att låta den växa genom hela kön.
BATCH_SIZE = 15

# Hur många gånger vi väntar på ledigt VRAM innan vi ger upp och kraschar
# (huvudappen har en hård 50%-gräns, så det här är bara ett skyddsnät).
VRAM_WAIT_RETRIES = 6
VRAM_WAIT_SECONDS = 10
VRAM_MIN_FREE_GB = 1.2


def _wait_for_free_vram() -> None:
    if not PLATE_READER_GPU:
        return

    import torch

    for attempt in range(1, VRAM_WAIT_RETRIES + 1):
        free_bytes, _total_bytes = torch.cuda.mem_get_info(0)
        free_gb = free_bytes / 1024**3
        if free_gb >= VRAM_MIN_FREE_GB:
            return
        print(
            f"Väntar på ledigt VRAM ({free_gb:.2f} GB fritt, behöver "
            f"{VRAM_MIN_FREE_GB} GB) — försök {attempt}/{VRAM_WAIT_RETRIES}..."
        )
        time.sleep(VRAM_WAIT_SECONDS)


def _run() -> None:
    print("ANPR-worker startar...")
    print(f"  Databas:      {DATABASE_PATH}")
    print(f"  GPU:          {PLATE_READER_GPU}")
    print(f"  Min konf:     {PLATE_MIN_CONFIDENCE}")
    print(f"  Skärpa-tröskel: {PLATE_READER_SHARPNESS_THRESHOLD}")
    print()

    db = Database(DATABASE_PATH)
    events = db.get_unprocessed_anpr_events()
    total = len(events)

    if total == 0:
        print("Inga events att bearbeta — alla har redan regnummer eller saknar snapshot.")
        db.close()
        return

    _wait_for_free_vram()

    print(f"Hittade {total} events utan regnummer. Laddar PlateReader...")
    plate_reader = PlateReader(gpu=PLATE_READER_GPU)
    print("PlateReader klar.\n")

    found = 0

    for i, event in enumerate(events, start=1):
        event_id = event["id"]
        result = process_event(event, plate_reader)

        if result is not None:
            plate_text, confidence = result
            db.update_event_plate(event_id, plate_text, confidence)
            found += 1
            print(f"[{i}/{total}] Event {event_id}: {plate_text}  konf={confidence:.2f}")
        else:
            db.mark_anpr_attempted(event_id)
            print(f"[{i}/{total}] Event {event_id}: inget regnummer hittat")

        if PLATE_READER_GPU and i % BATCH_SIZE == 0:
            import torch

            torch.cuda.empty_cache()

    print()
    print(f"Klar. Hittade regnummer i {found}/{total} events.")
    db.close()
    os._exit(0)


if __name__ == "__main__":
    main()
