from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database
from src.ccounter.plates import classify_plate


def main() -> None:
    db = Database(DATABASE_PATH)

    db.add_known_plate(
        plate_text="ABC123",
        label="Egen bil",
        group_name="own_vehicle",
        exclude_from_public_stats=True,
        exclude_from_internal_count=False,
        notes="Test av känt regnummer",
    )

    known_result = classify_plate(db.conn, "abc 123")
    unknown_result = classify_plate(db.conn, "xyz789")
    empty_result = classify_plate(db.conn, None)

    print("Known plate:")
    print(known_result)

    print("Unknown plate:")
    print(unknown_result)

    print("No plate:")
    print(empty_result)

    db.close()


if __name__ == "__main__":
    main()