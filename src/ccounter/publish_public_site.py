import os
from pathlib import Path

import paramiko

from src.ccounter.config import (
    WEB_UPLOAD_ENABLED,
    WEB_UPLOAD_METHOD,
    WEB_UPLOAD_HOST,
    WEB_UPLOAD_PORT,
    WEB_UPLOAD_USERNAME,
    WEB_UPLOAD_PASSWORD,
    WEB_UPLOAD_REMOTE_DIR,
    WEB_UPLOAD_UPLOAD_INDEX,
)
from src.ccounter.export_public_json import main as export_public_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = PROJECT_ROOT / "public"


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    current = ""

    for part in parts:
        current += f"/{part}"

        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def upload_file(
    sftp: paramiko.SFTPClient,
    local_path: Path,
    remote_dir: str,
) -> None:
    remote_path = f"{remote_dir.rstrip('/')}/{local_path.name}"

    print(f"Uploading {local_path} -> {remote_path}")
    sftp.put(str(local_path), remote_path)


def publish_via_sftp() -> None:
    if WEB_UPLOAD_METHOD.lower() != "sftp":
        raise ValueError("Only SFTP upload is supported right now.")

    if not WEB_UPLOAD_HOST:
        raise ValueError("WEB_UPLOAD_HOST saknas.")

    if not WEB_UPLOAD_USERNAME:
        raise ValueError("WEB_UPLOAD_USERNAME saknas.")

    if not WEB_UPLOAD_PASSWORD:
        raise ValueError("WEB_UPLOAD_PASSWORD saknas.")

    if not WEB_UPLOAD_REMOTE_DIR:
        raise ValueError("WEB_UPLOAD_REMOTE_DIR saknas.")

    index_path = PUBLIC_DIR / "index.html"
    stats_path = PUBLIC_DIR / "stats.json"

    if not stats_path.exists():
        raise FileNotFoundError(f"Saknar fil: {stats_path}")

    if WEB_UPLOAD_UPLOAD_INDEX and not index_path.exists():
        raise FileNotFoundError(f"Saknar fil: {index_path}")

    transport = paramiko.Transport((WEB_UPLOAD_HOST, WEB_UPLOAD_PORT))

    try:
        print(f"Connecting to {WEB_UPLOAD_HOST}:{WEB_UPLOAD_PORT}...")
        transport.connect(
            username=WEB_UPLOAD_USERNAME,
            password=WEB_UPLOAD_PASSWORD,
        )

        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            ensure_remote_dir(sftp, WEB_UPLOAD_REMOTE_DIR)

            if WEB_UPLOAD_UPLOAD_INDEX:
                upload_file(sftp, index_path, WEB_UPLOAD_REMOTE_DIR)

            upload_file(sftp, stats_path, WEB_UPLOAD_REMOTE_DIR)

        finally:
            sftp.close()

    finally:
        transport.close()

    print("Publish complete.")


def main() -> None:
    if not WEB_UPLOAD_ENABLED:
        print("WEB_UPLOAD_ENABLED=false. Skipping upload.")
        return

    print("Exporting public stats...")
    export_public_json()

    print("Publishing public site...")
    publish_via_sftp()


if __name__ == "__main__":
    main()