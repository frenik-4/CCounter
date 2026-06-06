import json
import os
from datetime import datetime

from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database


OUTPUT_PATH = "public/stats.json"


def main() -> None:
    db = Database(DATABASE_PATH)

    # --- Pass 1: aggregated totals per hour/category ---
    cursor = db.conn.execute(
        """
        SELECT
            strftime('%Y-%m-%d', timestamp) AS date,
            strftime('%Y-%m-%d %H:00:00', timestamp) AS hour_key,
            CAST(strftime('%H', timestamp) AS INTEGER) AS hour_num,
            COALESCE(final_category, object_class, 'unknown') AS category,
            COUNT(*) AS count
        FROM events
        WHERE excluded_from_public_stats = 0
          AND event_type NOT IN ('parking_entry', 'parking_exit')
          AND (final_category IS NULL OR final_category != 'parking_traffic')
          AND (object_class IS NULL OR object_class != 'person')
        GROUP BY date, hour_key, category
        ORDER BY date, hour_key, category;
        """
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
        hour_label = f"{hour_num:02d}:00-{hour_end:02d}:00"

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

    # --- Pass 2: safe individual events per hour (no plates, no track IDs) ---
    event_cursor = db.conn.execute(
        """
        SELECT
            strftime('%Y-%m-%d', timestamp) AS date,
            strftime('%Y-%m-%d %H:00:00', timestamp) AS hour_key,
            strftime('%H:%M', timestamp) AS time,
            event_type,
            object_class,
            COALESCE(final_category, object_class, 'unknown') AS category,
            direction
        FROM events
        WHERE excluded_from_public_stats = 0
          AND event_type NOT IN ('parking_entry', 'parking_exit')
          AND (final_category IS NULL OR final_category != 'parking_traffic')
          AND (object_class IS NULL OR object_class != 'person')
        ORDER BY timestamp;
        """
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

    output_days = {}

    for date, day in days.items():
        output_days[date] = {
            "total": day["total"],
            "road_traffic": day["road_traffic"],
            "other": day["other"],
            "categories": day["categories"],
            "hours": [hour for _, hour in sorted(day["hours"].items())],
        }

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "available_dates": sorted(available_dates),
        "days": output_days,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"Exported public stats to: {OUTPUT_PATH}")

    db.close()


if __name__ == "__main__":
    main()
