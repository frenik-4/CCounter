from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database
from src.ccounter.stats import (
    rebuild_hourly_public_stats,
    export_hourly_public_stats_to_csv,
)


def main() -> None:
    db = Database(DATABASE_PATH)

    rebuild_hourly_public_stats(db.conn)

    export_path = "exports/public_stats_hourly.csv"

    export_hourly_public_stats_to_csv(
        conn=db.conn,
        output_path=export_path,
    )

    print(f"Public stats exported to: {export_path}")

    db.close()


if __name__ == "__main__":
    main()