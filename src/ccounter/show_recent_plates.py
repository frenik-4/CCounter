"""
Visar de senaste ANPR-analyserade fordonen med träffar och missar.

Användning:
    python -m src.ccounter.show_recent_plates
    python -m src.ccounter.show_recent_plates --limit 100
"""

import argparse

from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Visa senaste ANPR-resultat")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Antal fordon att visa (default: 50)",
    )
    args = parser.parse_args()

    db = Database(DATABASE_PATH)

    rows = db.conn.execute(
        """
        SELECT
            timestamp,
            object_class,
            direction,
            plate_detected,
            plate_text,
            plate_confidence
        FROM events
        WHERE anpr_attempted = 1 OR plate_detected = 1
        ORDER BY id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()

    db.close()

    if not rows:
        print("Inga ANPR-analyserade fordon hittades.")
        return

    total = len(rows)
    found = sum(1 for r in rows if r["plate_detected"])
    hit_rate = found / total * 100

    print(f"Databas:  {DATABASE_PATH}")
    print(f"Visar:    senaste {total} analyserade fordon\n")

    col_ts    = 16
    col_class = 12
    col_dir   =  5
    col_plate = 10
    col_conf  =  6

    header = (
        f"{'Tidpunkt':<{col_ts}}  "
        f"{'Klass':<{col_class}}  "
        f"{'Riktn':<{col_dir}}  "
        f"{'Skylt':<{col_plate}}  "
        f"{'Konf':>{col_conf}}"
    )
    print(header)
    print("-" * len(header))

    for row in reversed(rows):
        direction = row["direction"] or "?"
        dir_short = "S" if direction == "A_TO_B" else "N" if direction == "B_TO_A" else direction

        if row["plate_detected"] and row["plate_text"]:
            plate = row["plate_text"].upper()
            conf  = f"{row['plate_confidence']:.2f}"
        else:
            plate = "-"
            conf  = ""

        print(
            f"{row['timestamp'][:16]:<{col_ts}}  "
            f"{(row['object_class'] or '?'):<{col_class}}  "
            f"{dir_short:<{col_dir}}  "
            f"{plate:<{col_plate}}  "
            f"{conf:>{col_conf}}"
        )

    print()
    print(f"{total} fordon analyserade, {found} regnummer hittade ({hit_rate:.0f}%)")


if __name__ == "__main__":
    main()
