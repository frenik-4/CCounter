"""
Exporterar säker, aggregerad trafikstatistik till public/stats.json.

Regler:
- Inga registreringsnummer, inga track-IDs, inga råa event-rader med privat data.
- Fotgängare filtreras bort (object_class='person' och final_category='pedestrian').
- Parkering filtreras bort.
- Bara de senaste EXPORT_MAX_DAYS dagarna exporteras.
"""

import json
import os
from datetime import datetime, timedelta

from src.ccounter.config import DATABASE_PATH, EXPORT_MAX_DAYS
from src.ccounter.database import Database


OUTPUT_PATH = "public/stats.json"

# Gemensamma WHERE-villkor för alla publika SQL-frågor.
# Observera: ingen plate_text, track_id eller snapshot_path exponeras.
_WHERE = """
    excluded_from_public_stats = 0
    AND event_type NOT IN ('parking_entry', 'parking_exit')
    AND (final_category IS NULL OR final_category NOT IN ('parking_traffic', 'pedestrian'))
    AND (object_class IS NULL OR object_class NOT IN ('person'))
    AND timestamp >= :cutoff
"""


def main() -> None:
    cutoff_date = datetime.now() - timedelta(days=EXPORT_MAX_DAYS)
    cutoff = cutoff_date.strftime("%Y-%m-%d")
    params = {"cutoff": cutoff}

    try:
        db = Database(DATABASE_PATH)
    except Exception as exc:
        print(f"Export avbröts — kunde inte öppna databasen: {exc}")
        return

    try:
        # --- Pass 1: aggregerade totaler per timme och kategori ---
        cursor = db.conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%d', timestamp)        AS date,
                strftime('%Y-%m-%d %H:00:00', timestamp) AS hour_key,
                CAST(strftime('%H', timestamp) AS INTEGER) AS hour_num,
                COALESCE(final_category, object_class, 'unknown') AS category,
                COUNT(*) AS count
            FROM events
            WHERE {_WHERE}
            GROUP BY date, hour_key, category
            ORDER BY date, hour_key, category;
            """,
            params,
        )

        days: dict[str, dict] = {}
        available_dates: set[str] = set()

        for row in cursor:
            date = row["date"]
            hour_key = row["hour_key"]
            hour_num = row["hour_num"]
            category = row["category"]
            count = row["count"]

            available_dates.add(date)

            if date not in days:
                days[date] = {
                    "total": 0,
                    "road_traffic": 0,
                    "other": 0,
                    "dir_south": 0,
                    "dir_north": 0,
                    "dir_unknown": 0,
                    "categories": {},
                    "hours": {},
                }

            day = days[date]
            day["total"] += count
            day["categories"][category] = day["categories"].get(category, 0) + count

            if category == "road_traffic":
                day["road_traffic"] += count
            else:
                day["other"] += count

            hour_end = (hour_num + 1) % 24
            hour_label = f"{hour_num:02d}:00–{hour_end:02d}:00"

            if hour_key not in day["hours"]:
                day["hours"][hour_key] = {
                    "hour": hour_label,
                    "road_traffic": 0,
                    "other": 0,
                    "total": 0,
                    "categories": {},
                    "events": [],
                }

            hour = day["hours"][hour_key]
            hour["total"] += count
            hour["categories"][category] = hour["categories"].get(category, 0) + count

            if category == "road_traffic":
                hour["road_traffic"] += count
            else:
                hour["other"] += count

        # --- Pass 2: individuella events per timme (inga reg.nr, inga track-IDs) ---
        event_cursor = db.conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%d', timestamp)        AS date,
                strftime('%Y-%m-%d %H:00:00', timestamp) AS hour_key,
                strftime('%H:%M', timestamp)           AS time,
                event_type,
                object_class,
                COALESCE(final_category, object_class, 'unknown') AS category,
                direction
            FROM events
            WHERE {_WHERE}
            ORDER BY timestamp;
            """,
            params,
        )

        for row in event_cursor:
            date = row["date"]
            hour_key = row["hour_key"]

            if date not in days or hour_key not in days[date]["hours"]:
                continue

            days[date]["hours"][hour_key]["events"].append({
                "time": row["time"],
                "event_type": row["event_type"],
                "object_class": row["object_class"] or "",
                "category": row["category"],
                "direction": row["direction"] or "",
            })

        # --- Pass 3: riktningsaggregering per dag ---
        dir_cursor = db.conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%d', timestamp) AS date,
                direction,
                COUNT(*) AS count
            FROM events
            WHERE {_WHERE}
              AND direction IS NOT NULL
              AND direction != ''
            GROUP BY date, direction;
            """,
            params,
        )

        for row in dir_cursor:
            date = row["date"]
            if date not in days:
                continue
            direction = row["direction"]
            count = row["count"]
            if direction == "A_TO_B":
                days[date]["dir_south"] += count
            elif direction == "B_TO_A":
                days[date]["dir_north"] += count
            else:
                days[date]["dir_unknown"] += count

        # --- Bygg output ---
        output_days = {}

        for date, day in days.items():
            output_days[date] = {
                "total": day["total"],
                "road_traffic": day["road_traffic"],
                "other": day["other"],
                "dir_south": day["dir_south"],
                "dir_north": day["dir_north"],
                "dir_unknown": day["dir_unknown"],
                "categories": day["categories"],
                "hours": [hour for _, hour in sorted(day["hours"].items())],
            }

        output = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "export_days": EXPORT_MAX_DAYS,
            "available_dates": sorted(available_dates),
            "days": output_days,
        }

        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

        with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)

        print(f"Exporterade publik statistik till: {OUTPUT_PATH}")
        print(f"  Dagar: {len(output_days)} | Events: {sum(len(d['hours']) for d in output_days.values())} timblock")

    except Exception as exc:
        print(f"Export misslyckades: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
