def line_side(
    point: tuple[int, int],
    line: tuple[int, int, int, int],
) -> float:
    px, py = point
    x1, y1, x2, y2 = line

    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


class LineCounter:
    def __init__(
        self,
        line_name: str,
        line: tuple[int, int, int, int],
    ):
        self.line_name = line_name
        self.line = line
        self.counted_ids: set[int] = set()
        self.total_count = 0

    def check_crossing(
        self,
        object_id: int,
        previous_point: tuple[int, int],
        current_point: tuple[int, int],
    ) -> str | None:
        if object_id in self.counted_ids:
            return None

        previous_side = line_side(previous_point, self.line)
        current_side = line_side(current_point, self.line)

        if previous_side == 0 or current_side == 0:
            return None

        crossed = previous_side * current_side < 0

        if not crossed:
            return None

        self.counted_ids.add(object_id)
        self.total_count += 1

        if previous_side < 0 and current_side > 0:
            return "A_TO_B"

        return "B_TO_A"


class MultiLineCounter:
    def __init__(
        self,
        lines: dict[str, tuple[int, int, int, int]],
    ):
        self.counters = {
            line_name: LineCounter(line_name, line)
            for line_name, line in lines.items()
        }

    def check_crossings(
        self,
        object_id: int,
        previous_point: tuple[int, int],
        current_point: tuple[int, int],
    ) -> list[dict]:
        crossings = []

        for line_name, counter in self.counters.items():
            direction = counter.check_crossing(
                object_id=object_id,
                previous_point=previous_point,
                current_point=current_point,
            )

            if direction is None:
                continue

            crossings.append(
                {
                    "line_name": line_name,
                    "direction": direction,
                }
            )

        return crossings

    def get_total(self) -> int:
        return sum(counter.total_count for counter in self.counters.values())

    def get_totals_by_line(self) -> dict[str, int]:
        return {
            line_name: counter.total_count
            for line_name, counter in self.counters.items()
        }