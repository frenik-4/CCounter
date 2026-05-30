import os
import time
from datetime import datetime

import cv2
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
)
from src.ccounter.database import Database


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

            detections.append(
                {
                    "class_id": class_id,
                    "class_name": model.names[class_id],
                    "confidence": confidence,
                    "bbox": (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                    ),
                }
            )

    return detections


def draw_detections(frame, detections) -> None:
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
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
    print("Startar CCounter med YOLO och sparning...")
    print(f"Laddar modell: {YOLO_MODEL}")

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
                        "Sparad upptäckt: "
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
                    f"Fordon i bild: {len(detections)} | "
                    f"Sparade totalt: {db.count_detections()}"
                )

            if SHOW_WINDOW:
                draw_detections(frame, detections)

                cv2.imshow("CCounter - YOLO vehicle detection", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

    finally:
        cap.release()
        db.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()