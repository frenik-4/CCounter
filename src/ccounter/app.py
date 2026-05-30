import os
import time
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO

from src.ccounter.config import (
    RTSP_URL,
    SHOW_WINDOW,
    YOLO_MODEL,
    CONFIDENCE_THRESHOLD,
    VEHICLE_CLASSES,
    DATABASE_PATH,
    SAVE_DETECTIONS,
    SAVE_SNAPSHOTS,
    SNAPSHOT_DIR,
    DETECTION_SAVE_INTERVAL_SECONDS,
    DETECTION_ZONE,
    DRAW_DETECTION_ZONE,
)
from src.ccounter.database import Database


os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def open_stream(rtsp_url: str) -> cv2.VideoCapture:
    print("Öppnar RTSP-ström...")

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        raise RuntimeError(
            "Kunde inte öppna RTSP-strömmen. "
            "Kontrollera RTSP_URL, lösenord, nätverk och kamera."
        )

    print("RTSP-ström öppnad.")
    return cap


def point_inside_zone(point: tuple[int, int]) -> bool:
    zone = np.array(DETECTION_ZONE, dtype=np.int32)
    result = cv2.pointPolygonTest(zone, point, False)

    return result >= 0


def detect_vehicles(model: YOLO, frame):
    results = model(
        frame,
        verbose=False,
        conf=CONFIDENCE_THRESHOLD,
    )

    detections = []

    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if class_id not in VEHICLE_CLASSES:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            x1 = int(x1)
            y1 = int(y1)
            x2 = int(x2)
            y2 = int(y2)

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)

            center = (center_x, center_y)

            if not point_inside_zone(center):
                continue

            detections.append(
                {
                    "class_id": class_id,
                    "class_name": model.names[class_id],
                    "confidence": confidence,
                    "bbox": (x1, y1, x2, y2),
                    "center": center,
                }
            )

    return detections


def draw_detection_zone(frame) -> None:
    if not DRAW_DETECTION_ZONE:
        return

    zone = np.array(DETECTION_ZONE, dtype=np.int32)

    cv2.polylines(
        frame,
        [zone],
        isClosed=True,
        color=(255, 255, 0),
        thickness=2,
    )

    cv2.putText(
        frame,
        "Detection zone",
        DETECTION_ZONE[0],
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2,
    )


def draw_detections(frame, detections) -> None:
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        center_x, center_y = detection["center"]
        class_name = detection["class_name"]
        confidence = detection["confidence"]

        label = f"{class_name} {confidence:.2f}"

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2,
        )

        cv2.circle(
            frame,
            (center_x, center_y),
            5,
            (0, 0, 255),
            -1,
        )

        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )


def save_snapshot(frame, detection: dict) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    class_name = detection["class_name"]
    confidence = detection["confidence"]

    filename = f"{timestamp}_{class_name}_{confidence:.2f}.jpg"
    snapshot_path = os.path.join(SNAPSHOT_DIR, filename)

    frame_to_save = frame.copy()
    draw_detection_zone(frame_to_save)
    draw_detections(frame_to_save, [detection])

    cv2.imwrite(snapshot_path, frame_to_save)

    return snapshot_path


def should_save_detection(
    detection: dict,
    last_saved_by_class: dict[str, float],
) -> bool:
    class_name = detection["class_name"]
    now = time.time()

    last_saved = last_saved_by_class.get(class_name)

    if last_saved is None:
        last_saved_by_class[class_name] = now
        return True

    seconds_since_last_save = now - last_saved

    if seconds_since_last_save >= DETECTION_SAVE_INTERVAL_SECONDS:
        last_saved_by_class[class_name] = now
        return True

    return False


def main() -> None:
    print("Startar CCounter med YOLO och detection zone...")
    print(f"Laddar modell: {YOLO_MODEL}")
    print(f"Detection zone: {DETECTION_ZONE}")

    model = YOLO(YOLO_MODEL)

    print("YOLO-modell laddad.")

    db = Database(DATABASE_PATH)
    cap = open_stream(RTSP_URL)

    frame_count = 0
    start_time = time.time()
    last_saved_by_class: dict[str, float] = {}

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("Ingen bild från kameran. Försöker igen...")
                time.sleep(1)
                continue

            frame_count += 1

            detections = detect_vehicles(model, frame)

            if SAVE_DETECTIONS:
                for detection in detections:
                    if not should_save_detection(detection, last_saved_by_class):
                        continue

                    snapshot_path = None

                    if SAVE_SNAPSHOTS:
                        snapshot_path = save_snapshot(frame, detection)

                    db.insert_detection(
                        class_name=detection["class_name"],
                        confidence=detection["confidence"],
                        snapshot_path=snapshot_path,
                    )

                    total = db.count_detections()

                    print(
                        "Sparad upptäckt inom zon: "
                        f"{detection['class_name']} | "
                        f"confidence={detection['confidence']:.2f} | "
                        f"total={total} | "
                        f"snapshot={snapshot_path}"
                    )

            if frame_count % 150 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0

                print(
                    f"FPS cirka: {fps:.1f} | "
                    f"Fordon i zon: {len(detections)} | "
                    f"Sparade totalt: {db.count_detections()}"
                )

            if SHOW_WINDOW:
                draw_detection_zone(frame)
                draw_detections(frame, detections)

                cv2.imshow("CCounter - Detection zone", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

    finally:
        cap.release()
        db.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()