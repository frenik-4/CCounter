import csv
import os
from datetime import datetime
from sqlite3 import Connection


def rebuild_hourly_public_stats(conn: Connection) -> None:
    """
    Bygger om public_stats_hourly från events.

    Viktigt:
    - tar bara med events där excluded_from_public_stats = 0
    - tar inte med plate_text
    - tar inte med snapshot_path
    """

    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("DELETE FROM public_stats_hourly;")

    conn.execute(
        """
        INSERT INTO public_stats_hourly (
            hour,
            category,
            event_type,
            direction,
            count,
            created_at
        )
        SELECT
            strftime('%Y-%m-%d %H:00:00', timestamp) AS hour,
            COALESCE(final_category, object_class, 'unknown') AS category,
            event_type,
            COALESCE(direction, 'unknown') AS direction,
            COUNT(*) AS count,
            ? AS created_at
        FROM events
        WHERE excluded_from_public_stats = 0
        GROUP BY
            hour,
            category,
            event_type,
            direction;
        """,
        (now,),
    )

    conn.commit()


def export_hourly_public_stats_to_csv(
    conn: Connection,
    output_path: str,
) -> None:
    """
    Exporterar endast publik statistik.
    Inga regnummer.
    Inga snapshots.
    Inga individuella events.
    """

    folder = os.path.dirname(output_path)

    if folder:
        os.makedirs(folder, exist_ok=True)

    cursor = conn.execute(
        """
        SELECT
            hour,
            category,
            event_type,
            direction,
            count
        FROM public_stats_hourly
        ORDER BY hour, category, event_type, direction;
        """
    )

    rows = cursor.fetchall()

    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "hour",
                "category",
                "event_type",
                "direction",
                "count",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row["hour"],
                    row["category"],
                    row["event_type"],
                    row["direction"],
                    row["count"],
                ]
            )