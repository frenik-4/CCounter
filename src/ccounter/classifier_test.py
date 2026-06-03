from src.ccounter.classifier import classify_object


def main() -> None:
    test_cases = [
        ("car", "main_count_line"),
        ("car", "parking_entry_line"),
        ("truck", "main_count_line"),
        ("person", "main_count_line"),
        ("bicycle", "main_count_line"),
        ("dog", "main_count_line"),
        ("horse", "main_count_line"),
        ("chair", "main_count_line"),
        (None, "main_count_line"),
    ]

    for object_class, line_name in test_cases:
        category = classify_object(
            object_class=object_class,
            line_name=line_name,
        )

        print(f"{object_class=} {line_name=} -> {category}")


if __name__ == "__main__":
    main()