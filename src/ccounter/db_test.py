from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database


def main() -> None:
    db = Database(DATABASE_PATH)

    db.insert_event(
        event_type="road_passage",
        track_id=1,
        object_class="car",
        final_category="road_traffic",
        direction="left_to_right",
        line_name="main_count_line",
        zone_name="road_zone",
        confidence=0.87,
        bbox=(100, 200, 300, 400),
        center=(200, 300),
        snapshot_path="data/snapshots/example.jpg",
    )

    db.add_known_plate(
        plate_text="ABC123",
        label="Testbil",
        group_name="own_vehicle",
        exclude_from_public_stats=True,
        notes="Testpost",
    )

    print(f"Events totalt: {db.count_events()}")
    print(f"Publika events: {db.count_public_events()}")

    db.close()


if __name__ == "__main__":
    main()