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

_WHERE = """
    excluded_from_public_stats = 0
    AND event_type NOT IN ('parking_entry', 'parking_exit')
    AND (final_category IS NULL OR final_category NOT IN ('parking_traffic', 'pedestrian'))
    AND (object_class IS NULL OR object_class NOT IN ('person'))
    AND timestamp >= :cutoff
"""

WEEKDAY_NAMES = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
_UPTIME_START_H = 6
_UPTIME_END_H = 22


def calculate_daily_uptime(conn, date_str: str) -> float | None:
    window_start = datetime.fromisoformat(f"{date_str} {_UPTIME_START_H:02d}:00:00")
    window_end = datetime.fromisoformat(f"{date_str} {_UPTIME_END_H:02d}:00:00")
    effective_end = min(window_end, datetime.now())

    if effective_end <= window_start:
        return None

    effective_seconds = (effective_end - window_start).total_seconds()

    cursor = conn.execute(
        "SELECT status FROM stream_events WHERE timestamp < ? ORDER BY timestamp DESC LIMIT 1",
        (window_start.isoformat(timespec="seconds"),),
    )
    row = cursor.fetchone()
    initial_state = row["status"] if row else None

    cursor = conn.execute(
        """
        SELECT timestamp, status FROM stream_events
        WHERE timestamp >= ? AND timestamp < ?
        ORDER BY timestamp
        """,
        (window_start.isoformat(timespec="seconds"), effective_end.isoformat(timespec="seconds")),
    )
    events = list(cursor)

    if initial_state is None and not events:
        return None

    current_state = initial_state or "down"
    current_time = window_start
    up_seconds = 0.0

    for event in events:
        event_time = datetime.fromisoformat(event["timestamp"])
        if current_state == "up":
            up_seconds += (event_time - current_time).total_seconds()
        current_state = event["status"]
        current_time = event_time

    if current_state == "up":
        up_seconds += (effective_end - current_time).total_seconds()

    return up_seconds / effective_seconds


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
                strftime('%Y-%m-%d', timestamp)          AS date,
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
                    "road_dir_south": 0,
                    "road_dir_north": 0,
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

        # --- Pass 2: individuella events per timme ---
        event_cursor = db.conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%d', timestamp)          AS date,
                strftime('%Y-%m-%d %H:00:00', timestamp) AS hour_key,
                strftime('%H:%M', timestamp)             AS time,
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

        # --- Pass 3: riktningsaggregering per dag (alla kategorier) ---
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

        # --- Pass 4: riktning per dag, endast road_traffic (för Excel-export) ---
        road_dir_cursor = db.conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%d', timestamp) AS date,
                direction,
                COUNT(*) AS count
            FROM events
            WHERE {_WHERE}
              AND final_category = 'road_traffic'
              AND direction IS NOT NULL
              AND direction != ''
            GROUP BY date, direction;
            """,
            params,
        )

        for row in road_dir_cursor:
            date = row["date"]
            if date not in days:
                continue
            direction = row["direction"]
            count = row["count"]
            if direction == "A_TO_B":
                days[date]["road_dir_south"] += count
            elif direction == "B_TO_A":
                days[date]["road_dir_north"] += count

        # --- Uptime per dag ---
        uptime_per_day: dict[str, float | None] = {
            date: calculate_daily_uptime(db.conn, date)
            for date in days
        }

        # --- Snitt per veckodag (bara dagar med uptime >= 95%) ---
        wd_road = [0] * 7
        wd_north = [0] * 7
        wd_south = [0] * 7
        wd_count = [0] * 7

        for date, day in days.items():
            uptime = uptime_per_day.get(date)
            if uptime is None or uptime < 0.95:
                continue
            wd = datetime.strptime(date, "%Y-%m-%d").weekday()
            wd_road[wd] += day["road_traffic"]
            wd_north[wd] += day["road_dir_north"]
            wd_south[wd] += day["road_dir_south"]
            wd_count[wd] += 1

        weekday_averages = [
            {
                "weekday": WEEKDAY_NAMES[i],
                "days_included": wd_count[i],
                "avg_road_traffic": round(wd_road[i] / wd_count[i], 1) if wd_count[i] > 0 else None,
                "avg_road_north": round(wd_north[i] / wd_count[i], 1) if wd_count[i] > 0 else None,
                "avg_road_south": round(wd_south[i] / wd_count[i], 1) if wd_count[i] > 0 else None,
            }
            for i in range(7)
        ]

        # --- Bygg output ---
        output_days = {}
        for date, day in days.items():
            uptime = uptime_per_day.get(date)
            output_days[date] = {
                "total": day["total"],
                "road_traffic": day["road_traffic"],
                "other": day["other"],
                "dir_south": day["dir_south"],
                "dir_north": day["dir_north"],
                "dir_unknown": day["dir_unknown"],
                "road_dir_south": day["road_dir_south"],
                "road_dir_north": day["road_dir_north"],
                "uptime_pct": round(uptime, 4) if uptime is not None else None,
                "categories": day["categories"],
                "hours": [hour for _, hour in sorted(day["hours"].items())],
            }

        output = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "export_days": EXPORT_MAX_DAYS,
            "available_dates": sorted(available_dates),
            "weekday_averages": weekday_averages,
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
