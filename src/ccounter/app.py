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
    SAVE_SNAPSHOTS,
    SNAPSHOT_DIR,
    DETECTION_ZONE,
    DRAW_DETECTION_ZONE,
    COUNT_LINE,
    DRAW_COUNT_LINE,
    LINES,
    DRAW_LINES,
    TRACKER_MAX_DISTANCE,
    TRACKER_MAX_MISSING_FRAMES,
)
from src.ccounter.database import Database
from src.ccounter.tracker import CentroidTracker
from src.ccounter.counter import MultiLineCounter


# Testa senare igen när ethernet är inkopplat.
# Vissa kameror fungerar bättre med TCP, andra sämre.
# os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def open_stream(rtsp_url: str) -> cv2.VideoCapture:
    print("Oppnar RTSP-strom...")

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        raise RuntimeError(
            "Kunde inte oppna RTSP-strommen. "
            "Kontrollera RTSP_URL, losenord, natverk och kamera."
        )

    print("RTSP-strom oppnad.")
    return cap


def point_inside_zone(point: tuple[int, int]) -> bool:
    zone = np.array(DETECTION_ZONE, dtype=np.int32)
    result = cv2.pointPolygonTest(zone, point, False)

    return result >= 0


def detect_vehicles(model: YOLO, frame) -> list[dict]:
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


def draw_count_line(frame) -> None:
    """
    Gammal enkel count line.
    Vi behåller den temporärt för jämförelse/debug.
    """
    if not DRAW_COUNT_LINE:
        return

    x1, y1, x2, y2 = COUNT_LINE

    cv2.line(
        frame,
        (x1, y1),
        (x2, y2),
        (0, 255, 255),
        3,
    )

    cv2.putText(
        frame,
        "Old count line",
        (x1, max(y1 - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )


def draw_lines(frame) -> None:
    """
    Nya konfigurerbara linjer från LINES.
    Dessa används för faktisk räkning.
    """
    if not DRAW_LINES:
        return

    for line_name, line in LINES.items():
        x1, y1, x2, y2 = line

        cv2.line(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 0, 255),
            3,
        )

        cv2.putText(
            frame,
            line_name,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )


def draw_tracked_objects(frame, tracked_objects: dict[int, dict]) -> None:
    for object_id, obj in tracked_objects.items():
        if obj.get("missing", 0) > 0:
            continue

        x1, y1, x2, y2 = obj["bbox"]
        center_x, center_y = obj["center"]

        class_name = obj["class_name"]
        confidence = obj["confidence"]

        label = f"ID {object_id} {class_name} {confidence:.2f}"

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


def save_passage_snapshot(
    frame,
    object_id: int,
    obj: dict,
    line_name: str,
    direction: str,
) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    class_name = obj["class_name"]
    confidence = obj["confidence"]

    filename = (
        f"{timestamp}_event_"
        f"id{object_id}_{class_name}_{line_name}_{direction}_{confidence:.2f}.jpg"
    )

    snapshot_path = os.path.join(SNAPSHOT_DIR, filename)

    frame_to_save = frame.copy()

    draw_detection_zone(frame_to_save)
    draw_count_line(frame_to_save)
    draw_lines(frame_to_save)
    draw_tracked_objects(frame_to_save, {object_id: obj})

    cv2.imwrite(snapshot_path, frame_to_save)

    return snapshot_path


def get_event_type_and_category(line_name: str) -> tuple[str, str]:
    if line_name == "parking_entry_line":
        return "parking_entry", "parking_traffic"

    if line_name == "parking_exit_line":
        return "parking_exit", "parking_traffic"

    return "road_passage", "road_traffic"


def handle_passages(
    db: Database,
    frame,
    tracked_objects: dict[int, dict],
    line_counter: MultiLineCounter,
) -> None:
    for object_id, obj in tracked_objects.items():
        if obj.get("missing", 0) > 0:
            continue

        previous_center = obj["previous_center"]
        current_center = obj["center"]

        crossings = line_counter.check_crossings(
            object_id=object_id,
            previous_point=previous_center,
            current_point=current_center,
        )

        for crossing in crossings:
            line_name = crossing["line_name"]
            direction = crossing["direction"]

            event_type, final_category = get_event_type_and_category(line_name)

            snapshot_path = None

            if SAVE_SNAPSHOTS:
                snapshot_path = save_passage_snapshot(
                    frame=frame,
                    object_id=object_id,
                    obj=obj,
                    line_name=line_name,
                    direction=direction,
                )

            db.insert_event(
                event_type=event_type,
                track_id=object_id,
                object_class=obj["class_name"],
                final_category=final_category,
                direction=direction,
                line_name=line_name,
                zone_name="road_zone",
                confidence=obj["confidence"],
                bbox=obj["bbox"],
                center=obj["center"],
                snapshot_path=snapshot_path,
            )

            total = db.count_events()

            print(
                "EVENT: "
                f"id={object_id} | "
                f"type={event_type} | "
                f"class={obj['class_name']} | "
                f"category={final_category} | "
                f"line={line_name} | "
                f"direction={direction} | "
                f"confidence={obj['confidence']:.2f} | "
                f"total={total} | "
                f"snapshot={snapshot_path}"
            )


def reconnect(rtsp_url: str, delay_seconds: int = 5) -> cv2.VideoCapture:
    print(f"Tappade strommen. Forsoker ateransluta om {delay_seconds} sekunder...")
    time.sleep(delay_seconds)
    return open_stream(rtsp_url)


def main() -> None:
    print("Startar CCounter med YOLO, tracking och flera linjer...")
    print(f"Modell: {YOLO_MODEL}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print(f"Detection zone: {DETECTION_ZONE}")
    print(f"Old count line: {COUNT_LINE}")
    print(f"Lines: {LINES}")

    model = YOLO(YOLO_MODEL)
    print("YOLO-modell laddad.")

    db = Database(DATABASE_PATH)

    tracker = CentroidTracker(
        max_distance=TRACKER_MAX_DISTANCE,
        max_missing_frames=TRACKER_MAX_MISSING_FRAMES,
    )

    line_counter = MultiLineCounter(LINES)

    cap = open_stream(RTSP_URL)

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                cap.release()

                try:
                    cap = reconnect(RTSP_URL)
                    continue
                except Exception as exc:
                    print(f"Ateranslutning misslyckades: {exc}")
                    continue

            frame_count += 1

            detections = detect_vehicles(model, frame)
            tracked_objects = tracker.update(detections)

            handle_passages(
                db=db,
                frame=frame,
                tracked_objects=tracked_objects,
                line_counter=line_counter,
            )

            if frame_count % 150 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0

                active_tracks = sum(
                    1
                    for obj in tracked_objects.values()
                    if obj.get("missing", 0) == 0
                )

                print(
                    f"FPS cirka: {fps:.1f} | "
                    f"Detections: {len(detections)} | "
                    f"Tracks: {active_tracks} | "
                    f"Events totalt: {db.count_events()}"
                )

            if SHOW_WINDOW:
                draw_detection_zone(frame)
                draw_count_line(frame)
                draw_lines(frame)
                draw_tracked_objects(frame, tracked_objects)

                cv2.putText(
                    frame,
                    f"Events: {db.count_events()}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                )

                cv2.imshow("CCounter - Tracking and multi-line counting", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

    finally:
        cap.release()
        db.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()