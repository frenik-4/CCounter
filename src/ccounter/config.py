import os
from dotenv import load_dotenv

load_dotenv()


def get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.lower() in ("true", "1", "yes", "y")


def get_int_set(name: str, default: set[int]) -> set[int]:
    value = os.getenv(name)

    if not value:
        return default

    return {int(x.strip()) for x in value.split(",")}


def get_polygon(name: str, default: list[tuple[int, int]]) -> list[tuple[int, int]]:
    value = os.getenv(name)

    if not value:
        return default

    points = []

    for point in value.split(";"):
        x, y = point.split(",")
        points.append((int(x.strip()), int(y.strip())))

    return points


def get_int_tuple(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    value = os.getenv(name)

    if not value:
        return default

    return tuple(int(x.strip()) for x in value.split(","))


RTSP_URL = os.getenv("RTSP_URL")
SHOW_WINDOW = get_bool("SHOW_WINDOW", True)

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

VEHICLE_CLASSES = get_int_set("VEHICLE_CLASSES", {2, 3, 5, 7})

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/ccounter.db")

SAVE_DETECTIONS = get_bool("SAVE_DETECTIONS", False)
SAVE_SNAPSHOTS = get_bool("SAVE_SNAPSHOTS", True)
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "data/snapshots")

DETECTION_SAVE_INTERVAL_SECONDS = int(
    os.getenv("DETECTION_SAVE_INTERVAL_SECONDS", "10")
)

DETECTION_ZONE = get_polygon(
    "DETECTION_ZONE",
    [
        (140, 285),
        (360, 270),
        (720, 240),
        (1040, 215),
        (1160, 205),
        (1240, 230),
        (1160, 285),
        (1040, 350),
        (760, 445),
        (300, 485),
        (140, 475),
    ],
)

DRAW_DETECTION_ZONE = get_bool("DRAW_DETECTION_ZONE", True)

COUNT_LINE = get_int_tuple("COUNT_LINE", (460, 440, 1040, 295))
DRAW_COUNT_LINE = get_bool("DRAW_COUNT_LINE", True)

TRACKER_MAX_DISTANCE = int(os.getenv("TRACKER_MAX_DISTANCE", "120"))
TRACKER_MAX_MISSING_FRAMES = int(os.getenv("TRACKER_MAX_MISSING_FRAMES", "25"))

BEST_OF_TWO_ENABLED = get_bool("BEST_OF_TWO_ENABLED", True)
BEST_OF_TWO_DELAY_SECONDS = float(os.getenv("BEST_OF_TWO_DELAY_SECONDS", "1.5"))

if not RTSP_URL:
    raise ValueError("RTSP_URL saknas. Lägg den i .env")