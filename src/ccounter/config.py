import os
from dotenv import load_dotenv

load_dotenv()


def get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.lower() in ("true", "1", "yes", "y")


RTSP_URL = os.getenv("RTSP_URL")
SHOW_WINDOW = get_bool("SHOW_WINDOW", True)

if not RTSP_URL:
    raise ValueError("RTSP_URL saknas. Lägg den i .env")