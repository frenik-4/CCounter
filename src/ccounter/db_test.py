import pytest
from src.ccounter.database import Database


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    yield db
    db.close()


def test_insert_and_count_event(db):
    assert db.count_events() == 0

    db.insert_event(
        event_type="road_passage",
        track_id=1,
        object_class="car",
        final_category="road_traffic",
        direction="A_TO_B",
        line_name="main_count_line",
        zone_name="road_zone",
        confidence=0.87,
        bbox=(100, 200, 300, 400),
        center=(200, 300),
        snapshot_path="data/snapshots/test.jpg",
    )

    assert db.count_events() == 1


def test_insert_event_with_plate(db):
    db.insert_event(
        event_type="road_passage",
        track_id=1,
        object_class="car",
        plate_detected=True,
        plate_text="ABC123",
        plate_confidence=0.91,
    )

    cursor = db.conn.execute("SELECT plate_detected, plate_text, plate_confidence FROM events WHERE id=1")
    row = cursor.fetchone()
    assert row["plate_detected"] == 1
    assert row["plate_text"] == "ABC123"
    assert abs(row["plate_confidence"] - 0.91) < 0.001


def test_excluded_event_not_in_public_count(db):
    db.insert_event(
        event_type="road_passage",
        track_id=1,
        object_class="car",
        excluded_from_public_stats=True,
    )
    db.insert_event(
        event_type="road_passage",
        track_id=2,
        object_class="car",
        excluded_from_public_stats=False,
    )

    assert db.count_events() == 2
    assert db.count_public_events() == 1


def test_add_known_plate(db):
    db.add_known_plate(
        plate_text="abc 123",
        label="Testbil",
        group_name="own_vehicle",
        exclude_from_public_stats=True,
        notes="Testpost",
    )

    cursor = db.conn.execute("SELECT plate_text, exclude_from_public_stats FROM known_plates")
    row = cursor.fetchone()
    assert row["plate_text"] == "ABC123"
    assert row["exclude_from_public_stats"] == 1


def test_add_known_plate_upsert(db):
    db.add_known_plate(plate_text="ABC123", label="First")
    db.add_known_plate(plate_text="ABC123", label="Second")

    cursor = db.conn.execute("SELECT COUNT(*) FROM known_plates")
    assert cursor.fetchone()[0] == 1
