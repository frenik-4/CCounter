from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database


def main() -> None:
    db = Database(DATABASE_PATH)

    cursor = db.conn.execute(
        """
        SELECT
            id,
            timestamp,
            event_type,
            object_class,
            final_category,
            direction,
            line_name,
            confidence,
            snapshot_path
        FROM events
        ORDER BY id DESC
        LIMIT 30;
        """
    )

    rows = cursor.fetchall()

    print(f"Database: {DATABASE_PATH}")
    print(f"Events found: {len(rows)}")
    print("")

    if not rows:
        print("No events found.")
        db.close()
        return

    for row in rows:
        confidence = row["confidence"]

        if confidence is None:
            confidence_text = "None"
        else:
            confidence_text = f"{confidence:.2f}"

        print(
            f"#{row['id']} | "
            f"{row['timestamp']} | "
            f"{row['event_type']} | "
            f"{row['object_class']} | "
            f"{row['final_category']} | "
            f"{row['direction']} | "
            f"{row['line_name']} | "
            f"conf={confidence_text} | "
            f"{row['snapshot_path']}"
        )

    db.close()


if __name__ == "__main__":
    main()