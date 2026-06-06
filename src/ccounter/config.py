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

def get_lines(name: str, default: dict[str, tuple[int, int, int, int]]) -> dict[str, tuple[int, int, int, int]]:
    value = os.getenv(name)

    if not value:
        return default

    lines = {}

    for line_config in value.split(";"):
        line_name, coordinates = line_config.split(":")
        x1, y1, x2, y2 = coordinates.split(",")

        lines[line_name.strip()] = (
            int(x1.strip()),
            int(y1.strip()),
            int(x2.strip()),
            int(y2.strip()),
        )

    return lines

LINES = get_lines(
    "LINES",
    {
        "main_count_line": (675, 195, 675, 420),
        "parking_entry_line": (420, 430, 950, 300),
    },
)

DRAW_LINES = get_bool("DRAW_LINES", True)

RTSP_URL = os.getenv("RTSP_URL")
SHOW_WINDOW = get_bool("SHOW_WINDOW", True)

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.40"))
DETECTION_DEBUG = get_bool("DETECTION_DEBUG", False)

VEHICLE_CLASSES = get_int_set("VEHICLE_CLASSES", {2, 3, 5, 7})
DETECTION_CLASSES = get_int_set(
    "DETECTION_CLASSES",
    {0, 1, 2, 3, 5, 7, 15, 16, 17, 18, 19},
)

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/ccounter.db")

SAVE_DETECTIONS = get_bool("SAVE_DETECTIONS", False)
SAVE_SNAPSHOTS = get_bool("SAVE_SNAPSHOTS", True)
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "data/snapshots")

DETECTION_SAVE_INTERVAL_SECONDS = int(
    os.getenv("DETECTION_SAVE_INTERVAL_SECONDS", "10")
)

PROCESS_EVERY_N_FRAMES = int(os.getenv("PROCESS_EVERY_N_FRAMES", "1"))

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

if PROCESS_EVERY_N_FRAMES > 1 and TRACKER_MAX_DISTANCE < PROCESS_EVERY_N_FRAMES * 100:
    import warnings
    warnings.warn(
        f"TRACKER_MAX_DISTANCE={TRACKER_MAX_DISTANCE} kan vara för litet när "
        f"PROCESS_EVERY_N_FRAMES={PROCESS_EVERY_N_FRAMES}. "
        f"Rekommenderat minimum: {PROCESS_EVERY_N_FRAMES * 100}.",
        stacklevel=2,
    )

DISPLAY_SCALE = float(os.getenv("DISPLAY_SCALE", "0.5"))

BEST_OF_TWO_ENABLED = get_bool("BEST_OF_TWO_ENABLED", True)
BEST_OF_TWO_DELAY_SECONDS = float(os.getenv("BEST_OF_TWO_DELAY_SECONDS", "1.5"))

WEB_UPLOAD_ENABLED = get_bool("WEB_UPLOAD_ENABLED", False)
WEB_UPLOAD_METHOD = os.getenv("WEB_UPLOAD_METHOD", "sftp")
WEB_UPLOAD_HOST = os.getenv("WEB_UPLOAD_HOST", "")
WEB_UPLOAD_PORT = int(os.getenv("WEB_UPLOAD_PORT", "22"))
WEB_UPLOAD_USERNAME = os.getenv("WEB_UPLOAD_USERNAME", "")
WEB_UPLOAD_PASSWORD = os.getenv("WEB_UPLOAD_PASSWORD", "")
WEB_UPLOAD_REMOTE_DIR = os.getenv("WEB_UPLOAD_REMOTE_DIR", "")
WEB_UPLOAD_UPLOAD_INDEX = get_bool("WEB_UPLOAD_UPLOAD_INDEX", True)

PLATE_RECOGNITION_ENABLED = get_bool("PLATE_RECOGNITION_ENABLED", False)
PLATE_LOG_PATH = os.getenv("PLATE_LOG_PATH", "data/plates_found.txt")
PLATE_MIN_CONFIDENCE = float(os.getenv("PLATE_MIN_CONFIDENCE", "0.30"))
PLATE_READER_GPU = get_bool("PLATE_READER_GPU", False)
PLATE_READER_SHARPNESS_THRESHOLD = float(os.getenv("PLATE_READER_SHARPNESS_THRESHOLD", "80.0"))

if not RTSP_URL:
    raise ValueError("RTSP_URL saknas. Lägg den i .env")