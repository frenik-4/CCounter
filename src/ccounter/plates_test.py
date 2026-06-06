import pytest
from src.ccounter.database import Database
from src.ccounter.plates import classify_plate, normalize_plate


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.add_known_plate(
        plate_text="ABC123",
        label="Egen bil",
        group_name="own_vehicle",
        exclude_from_public_stats=True,
    )
    yield db
    db.close()


def test_normalize_plate_strips_spaces_and_dashes():
    assert normalize_plate("abc 12-3") == "ABC123"


def test_known_plate_is_excluded_from_public(db):
    result = classify_plate(db.conn, "abc 123")
    assert result["plate_detected"] is True
    assert result["plate_text"] == "ABC123"
    assert result["plate_group"] == "own_vehicle"
    assert result["excluded_from_public_stats"] is True
    assert result["excluded_reason"] == "Egen bil"


def test_unknown_plate_is_not_excluded(db):
    result = classify_plate(db.conn, "XYZ789")
    assert result["plate_detected"] is True
    assert result["plate_text"] == "XYZ789"
    assert result["plate_group"] == "unknown"
    assert result["excluded_from_public_stats"] is False
    assert result["excluded_reason"] is None


def test_none_plate_returns_not_detected(db):
    result = classify_plate(db.conn, None)
    assert result["plate_detected"] is False
    assert result["plate_text"] is None
