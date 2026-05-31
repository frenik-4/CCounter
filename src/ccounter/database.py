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
        self.create_tables()

    def create_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                snapshot_path TEXT
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                object_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                direction TEXT NOT NULL,
                snapshot_path TEXT
            );
            """
        )

        self.conn.commit()

    def insert_detection(
        self,
        class_name: str,
        confidence: float,
        snapshot_path: str | None = None,
    ) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")

        self.conn.execute(
            """
            INSERT INTO detections (
                timestamp,
                class_name,
                confidence,
                snapshot_path
            )
            VALUES (?, ?, ?, ?);
            """,
            (
                timestamp,
                class_name,
                confidence,
                snapshot_path,
            ),
        )

        self.conn.commit()

    def insert_passage(
        self,
        object_id: int,
        class_name: str,
        confidence: float,
        direction: str,
        snapshot_path: str | None = None,
    ) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")

        self.conn.execute(
            """
            INSERT INTO passages (
                timestamp,
                object_id,
                class_name,
                confidence,
                direction,
                snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                timestamp,
                object_id,
                class_name,
                confidence,
                direction,
                snapshot_path,
            ),
        )

        self.conn.commit()

    def count_detections(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM detections;")
        return int(cursor.fetchone()[0])

    def count_passages(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM passages;")
        return int(cursor.fetchone()[0])

    def close(self) -> None:
        self.conn.close()