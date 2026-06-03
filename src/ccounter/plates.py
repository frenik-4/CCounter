from sqlite3 import Connection


def normalize_plate(plate_text: str) -> str:
    return plate_text.upper().replace(" ", "").replace("-", "")


def find_known_plate(
    conn: Connection,
    plate_text: str,
) -> dict | None:
    normalized = normalize_plate(plate_text)

    cursor = conn.execute(
        """
        SELECT
            plate_text,
            label,
            group_name,
            exclude_from_public_stats,
            exclude_from_internal_count,
            notes
        FROM known_plates
        WHERE plate_text = ?;
        """,
        (normalized,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def classify_plate(
    conn: Connection,
    plate_text: str | None,
) -> dict:
    if not plate_text:
        return {
            "plate_detected": False,
            "plate_text": None,
            "plate_group": None,
            "excluded_from_public_stats": False,
            "excluded_reason": None,
        }

    normalized = normalize_plate(plate_text)
    known = find_known_plate(conn, normalized)

    if known is None:
        return {
            "plate_detected": True,
            "plate_text": normalized,
            "plate_group": "unknown",
            "excluded_from_public_stats": False,
            "excluded_reason": None,
        }

    excluded_from_public_stats = bool(known["exclude_from_public_stats"])

    return {
        "plate_detected": True,
        "plate_text": normalized,
        "plate_group": known["group_name"],
        "excluded_from_public_stats": excluded_from_public_stats,
        "excluded_reason": known["label"] if excluded_from_public_stats else None,
    }