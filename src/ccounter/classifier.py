VEHICLE_CLASSES = {
    "car",
    "truck",
    "bus",
    "motorcycle",
}

ANIMAL_CLASSES = {
    "dog",
    "cat",
    "horse",
    "cow",
    "sheep",
}


def classify_object(
    object_class: str | None,
    line_name: str | None = None,
) -> str:
    """
    Returnerar CCounter-kategori baserat på YOLO-klass och eventuell linje.
    """

    if object_class is None:
        return "unknown"

    object_class = object_class.lower()

    if line_name == "parking_entry_line" and object_class in VEHICLE_CLASSES:
        return "parking_traffic"

    if line_name == "parking_exit_line" and object_class in VEHICLE_CLASSES:
        return "parking_traffic"

    if object_class in VEHICLE_CLASSES:
        return "road_traffic"

    if object_class == "person":
        return "pedestrian"

    if object_class == "bicycle":
        return "bicycle"

    if object_class == "horse":
        return "horse"

    if object_class in ANIMAL_CLASSES:
        return "animal"

    return "other"