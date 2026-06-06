from src.ccounter.classifier import classify_object


def test_car_on_main_line_is_road_traffic():
    assert classify_object("car", "main_count_line") == "road_traffic"


def test_truck_on_main_line_is_road_traffic():
    assert classify_object("truck", "main_count_line") == "road_traffic"


def test_car_on_parking_entry_is_parking_traffic():
    assert classify_object("car", "parking_entry_line") == "parking_traffic"


def test_car_on_parking_exit_is_parking_traffic():
    assert classify_object("car", "parking_exit_line") == "parking_traffic"


def test_truck_on_parking_entry_is_parking_traffic():
    assert classify_object("truck", "parking_entry_line") == "parking_traffic"


def test_person_is_pedestrian():
    assert classify_object("person", "main_count_line") == "pedestrian"


def test_bicycle_is_bicycle():
    assert classify_object("bicycle", "main_count_line") == "bicycle"


def test_horse_is_horse():
    assert classify_object("horse", "main_count_line") == "horse"


def test_dog_is_animal():
    assert classify_object("dog", "main_count_line") == "animal"


def test_unknown_class_is_other():
    assert classify_object("chair", "main_count_line") == "other"


def test_none_class_is_unknown():
    assert classify_object(None, "main_count_line") == "unknown"


def test_class_is_case_insensitive():
    assert classify_object("CAR", "main_count_line") == "road_traffic"
