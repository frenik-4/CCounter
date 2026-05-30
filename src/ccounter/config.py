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


RTSP_URL = os.getenv("RTSP_URL")
SHOW_WINDOW = get_bool("SHOW_WINDOW", True)

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))

VEHICLE_CLASSES = get_int_set("VEHICLE_CLASSES", {2, 3, 5, 7})

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/ccounter.db")

SAVE_DETECTIONS = get_bool("SAVE_DETECTIONS", True)
SAVE_SNAPSHOTS = get_bool("SAVE_SNAPSHOTS", True)
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "data/snapshots")
DETECTION_SAVE_INTERVAL_SECONDS = int(
    os.getenv("DETECTION_SAVE_INTERVAL_SECONDS", "10")
)

if not RTSP_URL:
    raise ValueError("RTSP_URL saknas. Lägg den i .env")