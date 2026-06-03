from src.ccounter.counter import MultiLineCounter


def main() -> None:
    lines = {
        "main_count_line": (100, 100, 100, 300),
        "parking_entry_line": (200, 100, 200, 300),
    }

    counter = MultiLineCounter(lines)

    object_id = 1

    # Objektet rör sig från vänster till höger.
    points = [
        (50, 200),
        (120, 200),
        (180, 200),
        (220, 200),
    ]

    for previous_point, current_point in zip(points, points[1:]):
        crossings = counter.check_crossings(
            object_id=object_id,
            previous_point=previous_point,
            current_point=current_point,
        )

        for crossing in crossings:
            print(
                f"Object {object_id} crossed "
                f"{crossing['line_name']} "
                f"direction={crossing['direction']}"
            )

    print(f"Total: {counter.get_total()}")
    print(f"By line: {counter.get_totals_by_line()}")


if __name__ == "__main__":
    main()