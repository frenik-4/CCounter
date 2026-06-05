import json
import os
from collections import defaultdict
from datetime import datetime

from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database


OUTPUT_PATH = "public/stats.json"


def translate_hour(timestamp: str) -> tuple[str, str, str]:
    """
    Returnerar:
    date = 2026-06-03
    hour_key = 2026-06-03 08:00:00
    hour_label = 08:00-09:00
    """

    dt = datetime.fromisoformat(timestamp)

    date = dt.strftime("%Y-%m-%d")
    hour_key = dt.strftime("%Y-%m-%d %H:00:00")
    hour_start = dt.strftime("%H:00")
    hour_end = dt.replace(hour=dt.hour + 1).strftime("%H:00") if dt.hour < 23 else "00:00"

    return date, hour_key, f"{hour_start}-{hour_end}"


def is_public_event(row) -> bool:
    if row["excluded_from_public_stats"]:
        return False

    # Tillfälligt: publicera inte parking i publika dashboarden
    if row["event_type"] in ("parking_entry", "parking_exit"):
        return False

    if row["final_category"] == "parking_traffic":
        return False

    return True


def main() -> None:
    db = Database(DATABASE_PATH)

    cursor = db.conn.execute(
        """
        SELECT
            timestamp,
            event_type,
            object_class,
            final_category,
            direction,
            line_name,
            confidence,
            excluded_from_public_stats
        FROM events
        ORDER BY timestamp ASC;
        """
    )

    rows = cursor.fetchall()

    days = {}
    available_dates = set()

    for row in rows:
        if not is_public_event(row):
            continue

        date, hour_key, hour_label = translate_hour(row["timestamp"])
        available_dates.add(date)

        if date not in days:
            days[date] = {
                "total": 0,
                "road_traffic": 0,
                "other": 0,
                "categories": defaultdict(int),
                "hours_by_key": {},
            }

        day = days[date]

        category = row["final_category"] or row["object_class"] or "unknown"

        if category == "road_traffic":
            day["road_traffic"] += 1
        else:
            day["other"] += 1

        day["total"] += 1
        day["categories"][category] += 1

        if hour_key not in day["hours_by_key"]:
            day["hours_by_key"][hour_key] = {
                "hour": hour_label,
                "road_traffic": 0,
                "other": 0,
                "total": 0,
                "events": [],
            }

        hour = day["hours_by_key"][hour_key]

        if category == "road_traffic":
            hour["road_traffic"] += 1
        else:
            hour["other"] += 1

        hour["total"] += 1

        event_time = datetime.fromisoformat(row["timestamp"]).strftime("%H:%M:%S")

        hour["events"].append(
            {
                "time": event_time,
                "event_type": row["event_type"],
                "category": category,
                "object_class": row["object_class"],
                "direction": row["direction"],
            }
        )

    output_days = {}

    for date, day in days.items():
        hours = [
            hour
            for _, hour in sorted(day["hours_by_key"].items())
        ]

        output_days[date] = {
            "total": day["total"],
            "road_traffic": day["road_traffic"],
            "other": day["other"],
            "categories": dict(day["categories"]),
            "hours": hours,
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