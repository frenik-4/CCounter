import csv
import pytest
from src.ccounter.database import Database
from src.ccounter.stats import rebuild_hourly_public_stats, export_hourly_public_stats_to_csv


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))

    db.insert_event(event_type="road_passage", object_class="car", final_category="road_traffic", direction="A_TO_B")
    db.insert_event(event_type="road_passage", object_class="car", final_category="road_traffic", direction="B_TO_A")
    db.insert_event(event_type="road_passage", object_class="person", final_category="pedestrian", direction="A_TO_B")
    db.insert_event(event_type="road_passage", object_class="car", final_category="road_traffic", excluded_from_public_stats=True)

    yield db
    db.close()


def test_rebuild_hourly_stats_excludes_private_events(db):
    rebuild_hourly_public_stats(db.conn)

    cursor = db.conn.execute("SELECT SUM(count) FROM public_stats_hourly")
    total = cursor.fetchone()[0]
    assert total == 3


def test_rebuild_hourly_stats_is_idempotent(db):
    rebuild_hourly_public_stats(db.conn)
    rebuild_hourly_public_stats(db.conn)

    cursor = db.conn.execute("SELECT SUM(count) FROM public_stats_hourly")
    total = cursor.fetchone()[0]
    assert total == 3


def test_export_hourly_stats_to_csv(db, tmp_path):
    rebuild_hourly_public_stats(db.conn)
    output_path = str(tmp_path / "stats.csv")
    export_hourly_public_stats_to_csv(db.conn, output_path)

    with open(output_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) > 0
    assert "hour" in rows[0]
    assert "category" in rows[0]
    assert "count" in rows[0]
