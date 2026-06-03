import os
import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

        folder = os.path.dirname(db_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        self.create_tables()

    def create_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                timestamp TEXT NOT NULL,

                event_type TEXT NOT NULL,
                track_id INTEGER,
                object_class TEXT,
                final_category TEXT,

                direction TEXT,
                line_name TEXT,
                zone_name TEXT,

                confidence REAL,

                bbox_x1 INTEGER,
                bbox_y1 INTEGER,
                bbox_x2 INTEGER,
                bbox_y2 INTEGER,
                center_x INTEGER,
                center_y INTEGER,

                plate_detected INTEGER DEFAULT 0,
                plate_text TEXT,
                plate_confidence REAL,
                plate_group TEXT,

                excluded_from_public_stats INTEGER DEFAULT 0,
                excluded_reason TEXT,

                snapshot_path TEXT,

                created_at TEXT NOT NULL
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS known_plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                plate_text TEXT NOT NULL UNIQUE,
                label TEXT,
                group_name TEXT,

                exclude_from_public_stats INTEGER DEFAULT 0,
                exclude_from_internal_count INTEGER DEFAULT 0,

                notes TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public_stats_hourly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                hour TEXT NOT NULL,
                category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                direction TEXT,

                count INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE(hour, category, event_type, direction)
            );
            """
        )

        self.conn.commit()

    def insert_event(
        self,
        event_type: str,
        track_id: int | None = None,
        object_class: str | None = None,
        final_category: str | None = None,
        direction: str | None = None,
        line_name: str | None = None,
        zone_name: str | None = None,
        confidence: float | None = None,
        bbox: tuple[int, int, int, int] | None = None,
        center: tuple[int, int] | None = None,
        plate_detected: bool = False,
        plate_text: str | None = None,
        plate_confidence: float | None = None,
        plate_group: str | None = None,
        excluded_from_public_stats: bool = False,
        excluded_reason: str | None = None,
        snapshot_path: str | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")

        bbox_x1 = bbox_y1 = bbox_x2 = bbox_y2 = None
        if bbox is not None:
            bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox

        center_x = center_y = None
        if center is not None:
            center_x, center_y = center

        self.conn.execute(
            """
            INSERT INTO events (
                timestamp,
                event_type,
                track_id,
                object_class,
                final_category,
                direction,
                line_name,
                zone_name,
                confidence,
                bbox_x1,
                bbox_y1,
                bbox_x2,
                bbox_y2,
                center_x,
                center_y,
                plate_detected,
                plate_text,
                plate_confidence,
                plate_group,
                excluded_from_public_stats,
                excluded_reason,
                snapshot_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                now,
                event_type,
                track_id,
                object_class,
                final_category,
                direction,
                line_name,
                zone_name,
                confidence,
                bbox_x1,
                bbox_y1,
                bbox_x2,
                bbox_y2,
                center_x,
                center_y,
                int(plate_detected),
                plate_text,
                plate_confidence,
                plate_group,
                int(excluded_from_public_stats),
                excluded_reason,
                snapshot_path,
                now,
            ),
        )

        self.conn.commit()

    def add_known_plate(
        self,
        plate_text: str,
        label: str | None = None,
        group_name: str | None = None,
        exclude_from_public_stats: bool = False,
        exclude_from_internal_count: bool = False,
        notes: str | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")

        self.conn.execute(
            """
            INSERT OR REPLACE INTO known_plates (
                plate_text,
                label,
                group_name,
                exclude_from_public_stats,
                exclude_from_internal_count,
                notes,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                plate_text.upper().replace(" ", ""),
                label,
                group_name,
                int(exclude_from_public_stats),
                int(exclude_from_internal_count),
                notes,
                now,
                now,
            ),
        )

        self.conn.commit()

    def count_events(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM events;")
        return int(cursor.fetchone()[0])

    def count_public_events(self) -> int:
        cursor = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE excluded_from_public_stats = 0;
            """
        )
        return int(cursor.fetchone()[0])

    def close(self) -> None:
        self.conn.close()