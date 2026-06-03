from src.ccounter.config import LINES, DRAW_LINES


def main() -> None:
    print("Configured lines:")

    for name, line in LINES.items():
        print(f"{name}: {line}")

    print(f"DRAW_LINES: {DRAW_LINES}")


if __name__ == "__main__":
    main()