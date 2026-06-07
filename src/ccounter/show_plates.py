"""
Visar hittade registreringsskyltar från databasen.

Grupperar per unik skylt och visar antal passager, konfidens och senast sedd.
Flaggar tveksamma läsningar (låg konfidens eller felaktig fordonsklass).

Användning:
    python -m src.ccounter.show_plates
    python -m src.ccounter.show_plates --min-conf 0.60
    python -m src.ccounter.show_plates --all        # visa även tveksamma
"""

import argparse

from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database

# Klasser där en skyltläsning troligen är ett falskt positiv
_UNEXPECTED_CLASSES = {"person", "bicycle", "dog", "cat", "horse", "cow", "sheep"}

# Svenska fordonsregistreringsnummer: 3 bokstäver + 3 siffror (+ ev. bokstav)
# Andra format (SRS65H, KXB70E etc.) är troligen felläsningar
def _looks_swedish(plate: str) -> bool:
    p = plate.upper().replace(" ", "")
    if len(p) == 6:
        return p[:3].isalpha() and p[3:].isdigit()
    if len(p) == 7:
        return p[:3].isalpha() and p[3:6].isdigit() and p[6].isalpha()
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Visa hittade registreringsskyltar")
    parser.add_argument(
        "--min-conf",
        type=float,
        default=0.50,
        metavar="X",
        help="Minsta konfidens att visa (default: 0.50)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Visa alla, inkl. låg konfidens och troliga felläsningar",
    )
    args = parser.parse_args()

    db = Database(DATABASE_PATH)

    rows = db.conn.execute(
        """
        SELECT
            plate_text,
            plate_confidence,
            timestamp,
            object_class,
            direction,
            snapshot_path
        FROM events
        WHERE plate_detected = 1
          AND plate_text IS NOT NULL
          AND plate_text != ''
        ORDER BY plate_text, timestamp
        """
    ).fetchall()

    db.close()

    if not rows:
        print("Inga registreringsskyltar hittade i databasen.")
        return

    # Gruppera per skylt
    plates: dict[str, dict] = {}
    for row in rows:
        text = row["plate_text"].upper().strip()
        if text not in plates:
            plates[text] = {
                "count": 0,
                "best_conf": 0.0,
                "last_seen": "",
                "first_seen": row["timestamp"],
                "classes": set(),
                "directions": set(),
                "snapshot": row["snapshot_path"],
            }
        p = plates[text]
        p["count"] += 1
        p["last_seen"] = row["timestamp"]
        if row["plate_confidence"] > p["best_conf"]:
            p["best_conf"] = row["plate_confidence"]
            p["snapshot"] = row["snapshot_path"]
        p["classes"].add(row["object_class"] or "?")
        if row["direction"]:
            p["directions"].add(row["direction"])

    # Filtrera
    filtered = {}
    skipped = 0
    for text, p in plates.items():
        suspicious = (
            p["best_conf"] < args.min_conf
            or bool(p["classes"] & _UNEXPECTED_CLASSES)
            or not _looks_swedish(text)
        )
        if suspicious and not args.all:
            skipped += 1
            continue
        filtered[text] = p

    # Sortera: fler passager först, sedan alfabetiskt
    sorted_plates = sorted(
        filtered.items(),
        key=lambda x: (-x[1]["count"], x[0]),
    )

    # Skriv ut
    min_conf_display = args.min_conf if not args.all else 0.0
    print(f"Databas:  {DATABASE_PATH}")
    print(f"Filter:   konfidens >= {min_conf_display:.2f}  |  {'alla klasser' if args.all else 'fordon endast'}")
    print(f"Hittade:  {len(sorted_plates)} unika skyltar  ({skipped} filtrerade bort)")
    print()

    if not sorted_plates:
        print("Inga skyltar matchar filtret. Prova --all eller --min-conf 0.30")
        return

    col_plate  = 10
    col_count  =  5
    col_conf   =  6
    col_dir    = 10
    col_first  = 17
    col_last   = 17

    header = (
        f"{'Skylt':<{col_plate}}  "
        f"{'Ggr':>{col_count}}  "
        f"{'Konf':>{col_conf}}  "
        f"{'Riktning':<{col_dir}}  "
        f"{'Forsta sedd':<{col_first}}  "
        f"Senast sedd"
    )
    print(header)
    print("-" * len(header))

    for text, p in sorted_plates:
        directions = "/".join(
            ("S" if d == "A_TO_B" else "N" if d == "B_TO_A" else d)
            for d in sorted(p["directions"])
        ) or "–"

        suspicious_flag = ""
        if p["best_conf"] < args.min_conf:
            suspicious_flag = " !"
        elif bool(p["classes"] & _UNEXPECTED_CLASSES):
            suspicious_flag = " ?"

        print(
            f"{text:<{col_plate}}  "
            f"{p['count']:>{col_count}}  "
            f"{p['best_conf']:>{col_conf}.2f}  "
            f"{directions:<{col_dir}}  "
            f"{p['first_seen'][:16]:<{col_first}}  "
            f"{p['last_seen'][:16]}"
            f"{suspicious_flag}"
        )

    print()
    print(f"Totalt {sum(p['count'] for _, p in sorted_plates)} skyltobservationer.")


if __name__ == "__main__":
    main()
