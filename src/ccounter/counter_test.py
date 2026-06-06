import pytest
from src.ccounter.counter import LineCounter, MultiLineCounter


def test_line_counter_crossing_left_to_right():
    # Vertical line at x=100 going downward: left side is B, right side is A.
    counter = LineCounter("line", (100, 100, 100, 300))
    direction = counter.check_crossing(1, (50, 200), (150, 200))
    assert direction == "B_TO_A"
    assert counter.total_count == 1


def test_line_counter_crossing_right_to_left():
    counter = LineCounter("line", (100, 100, 100, 300))
    direction = counter.check_crossing(1, (150, 200), (50, 200))
    assert direction == "A_TO_B"
    assert counter.total_count == 1


def test_line_counter_no_crossing():
    counter = LineCounter("line", (100, 100, 100, 300))
    direction = counter.check_crossing(1, (50, 200), (80, 200))
    assert direction is None
    assert counter.total_count == 0


def test_line_counter_counts_each_id_once():
    counter = LineCounter("line", (100, 100, 100, 300))
    counter.check_crossing(1, (50, 200), (150, 200))
    second = counter.check_crossing(1, (150, 200), (50, 200))
    assert second is None
    assert counter.total_count == 1


def test_line_counter_different_ids_counted_independently():
    counter = LineCounter("line", (100, 100, 100, 300))
    counter.check_crossing(1, (50, 200), (150, 200))
    counter.check_crossing(2, (50, 200), (150, 200))
    assert counter.total_count == 2


def test_multi_line_counter_crossings():
    lines = {
        "main_count_line": (100, 100, 100, 300),
        "parking_entry_line": (200, 100, 200, 300),
    }
    counter = MultiLineCounter(lines)

    crossings = counter.check_crossings(1, (50, 200), (250, 200))

    line_names = {c["line_name"] for c in crossings}
    assert "main_count_line" in line_names
    assert "parking_entry_line" in line_names
    assert counter.get_total() == 2


def test_multi_line_counter_no_crossing():
    lines = {"main_count_line": (100, 100, 100, 300)}
    counter = MultiLineCounter(lines)
    crossings = counter.check_crossings(1, (50, 200), (80, 200))
    assert crossings == []


def test_multi_line_counter_get_totals_by_line():
    lines = {
        "line_a": (100, 100, 100, 300),
        "line_b": (200, 100, 200, 300),
    }
    counter = MultiLineCounter(lines)
    counter.check_crossings(1, (50, 200), (250, 200))
    totals = counter.get_totals_by_line()
    assert totals["line_a"] == 1
    assert totals["line_b"] == 1
