import json
import os
import queue
import threading
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
    DETECTION_CLASSES,
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
    DISPLAY_SCALE,
    PROCESS_EVERY_N_FRAMES,
    DETECTION_DEBUG,
    PLATE_MIN_CONFIDENCE,
    PLATE_READER_GPU,
    PLATE_READER_SHARPNESS_THRESHOLD,
)
from src.ccounter.database import Database
from src.ccounter.tracker import CentroidTracker
from src.ccounter.counter import MultiLineCounter
from src.ccounter.classifier import classify_object
from src.ccounter.config import ANPR_MIN_BBOX_WIDTH, PLATE_CAPTURE_Y, PLATE_CAPTURE_Y_TOLERANCE
from src.ccounter.ov_detector import OVDetector
from src.ccounter.plate_reader import PlateReader
from src.ccounter.track_plate_manager import TrackPlateManager, PlateCandidate


# Undertryck FFmpeg/libavcodec varningar (t.ex. H.264 macroblock-fel) som
# annars svämmar över journald och kan låsa systemet vid dålig RTSP-signal.
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "fatal"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def open_stream(rtsp_url: str) -> cv2.VideoCapture:
    print("Oppnar RTSP-strom...")

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        raise RuntimeError(
            "Kunde inte oppna RTSP-strommen. "
            "Kontrollera RTSP_URL, losenord, natverk och kamera."
        )

    # Begränsa intern buffert till 1 frame så att cap.read() alltid
    # returnerar aktuell frame — inte en uppsamlad backlog från strömmen.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print("RTSP-strom oppnad.")
    return cap


def point_inside_zone(point: tuple[int, int]) -> bool:
    zone = np.array(DETECTION_ZONE, dtype=np.int32)
    result = cv2.pointPolygonTest(zone, point, False)

    return result >= 0


def detect_vehicles(model, frame) -> list[dict]:
    if isinstance(model, OVDetector):
        raw = model(frame, conf=CONFIDENCE_THRESHOLD)
    else:
        raw = []
        for result in model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD):
            for box in result.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                raw.append({
                    "class_id":   int(box.cls[0]),
                    "class_name": model.names[int(box.cls[0])],
                    "confidence": float(box.conf[0]),
                    "bbox":       (x1, y1, x2, y2),
                    "center":     ((x1 + x2) // 2, (y1 + y2) // 2),
                })

    detections = []
    for det in raw:
        class_id = det["class_id"]
        center = det["center"]

        if class_id not in DETECTION_CLASSES:
            if DETECTION_DEBUG:
                print(f"DEBUG skip fel_klass: {det['class_name']} (id={class_id}) conf={det['confidence']:.2f} center={center}")
            continue

        if not point_inside_zone(center):
            if DETECTION_DEBUG:
                print(f"DEBUG skip utanfor_zon: {det['class_name']} conf={det['confidence']:.2f} center={center}")
            continue

        detections.append(det)

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
    draw_tracked_objects(frame_to_save, {object_id: obj})
    cv2.imwrite(snapshot_path, frame_to_save)

    return snapshot_path


class BestCropTracker:
    """
    Spårar den skarpaste fordonscroppen per track ID i realtid — ingen OCR.
    Används för att ge anpr_worker bästa möjliga bildunderlag vid korsning.
    """

    VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

    MIN_BBOX_WIDTH = ANPR_MIN_BBOX_WIDTH

    TOP_N = 5
    CAPTURE_Y = PLATE_CAPTURE_Y
    CAPTURE_Y_TOLERANCE = PLATE_CAPTURE_Y_TOLERANCE

    def __init__(self) -> None:
        self._candidates: dict[int, list[tuple[float, np.ndarray]]] = {}
        self._y_triggered: set[int] = set()

    def update(self, track_id: int, frame, bbox: tuple[int, int, int, int]) -> None:
        x1, y1, x2, y2 = bbox
        fh, fw = frame.shape[:2]
        w = x2 - x1
        h = y2 - y1

        # Hoppa över frames där fordonet är för smalt i bild — t.ex. när det
        # precis dyker upp bakom vegetation och knappt är synligt. Utan detta
        # väljs ofta det allra första frame med hög kantkontrast (strålkastare
        # mot mörk bakgrund) trots att skylten inte alls är synlig.
        if w < self.MIN_BBOX_WIDTH:
            return

        # Horisontell padding: 5 % på varje sida.
        # Vertikal padding nedtill: 15 % extra — fångar frontplåten som
        # ofta hamnar precis under YOLO-bbox vid frontala genomkörningar.
        padding_x = int(w * 0.05)
        padding_y_bottom = int(h * 0.15)

        cx1 = max(0, x1 - padding_x)
        cx2 = min(fw, x2 + padding_x)
        cy1 = max(0, y1)
        cy2 = min(fh, y2 + padding_y_bottom)

        if cx2 <= cx1 or cy2 <= cy1:
            return

        crop = frame[cy1:cy2, cx1:cx2]

        # Skärpemätning på den tight (opadded) delen — undvik att bakgrunden
        # under bilen påverkar Laplacian-variansen.
        tight = frame[max(0, y1):min(fh, y2), max(0, x1):min(fw, x2)]
        if tight.size == 0:
            return
        gray = cv2.cvtColor(tight, cv2.COLOR_BGR2GRAY)

        # Klippa övermättade pixlar (strålkastare, IR-reflex) innan skärpemätning.
        # Utan klippning dominerar ljuskällor Laplacian-variansen trots att bilden
        # i övrigt är rörelseoskarp — särskilt påtagligt på natten.
        gray_clipped = np.clip(gray, 0, 180)
        sharpness = float(cv2.Laplacian(gray_clipped, cv2.CV_64F).var())

        # Positionsbaserad trigger: om fordonet är på optimal Y-position
        # får framen maxprioritet och hamnar alltid först i top-N.
        center_y = (y1 + y2) // 2
        if (
            self.CAPTURE_Y > 0
            and track_id not in self._y_triggered
            and abs(center_y - self.CAPTURE_Y) <= self.CAPTURE_Y_TOLERANCE
        ):
            self._y_triggered.add(track_id)
            sharpness = 1e9

        candidates = self._candidates.setdefault(track_id, [])
        candidates.append((sharpness, crop.copy()))
        candidates.sort(key=lambda x: -x[0])
        if len(candidates) > self.TOP_N:
            candidates.pop()

    def get_all(self, track_id: int) -> list[np.ndarray]:
        return [crop for _, crop in self._candidates.get(track_id, [])]

    def get(self, track_id: int) -> np.ndarray | None:
        crops = self.get_all(track_id)
        return crops[0] if crops else None

    def remove(self, track_id: int) -> None:
        self._candidates.pop(track_id, None)
        self._y_triggered.discard(track_id)


class PlateOCRWorker:
    """
    Kör EasyOCR i en bakgrundstråd så att OCR-anrop (1–3 s) inte blockerar
    huvudloopen. Main-tråden croppar fordonet och lägger i kö; bakgrunds-
    tråden kör skärpekontroll, OCR och röstning per track_id.
    """

    def __init__(self) -> None:
        print("Laddar EasyOCR för live-skyltläsning...")
        self._reader = PlateReader(gpu=PLATE_READER_GPU)
        self._min_conf = PLATE_MIN_CONFIDENCE
        self._sharpness_threshold = PLATE_READER_SHARPNESS_THRESHOLD
        self._candidates: dict[int, PlateCandidate] = {}
        self._lock = threading.Lock()
        # Kö med max 40 crops — droppa om tråden hänger efter.
        self._q: queue.Queue = queue.Queue(maxsize=40)
        self._thread = threading.Thread(target=self._run, daemon=True, name="plate-ocr")
        self._thread.start()
        print("EasyOCR-tråd startad.")

    def submit(self, track_id: int, frame, bbox: tuple[int, int, int, int]) -> None:
        """Croppar fordon och lägger i kö. Droppar tyst om kön är full."""
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        h = y2 - y1
        plate_y1 = max(0, y1 + int(h * 0.20))
        plate_y2 = min(fh, y1 + int(h * 0.80))
        pad_x = int((x2 - x1) * 0.05)
        cx1, cx2 = max(0, x1 - pad_x), min(fw, x2 + pad_x)
        if cx2 <= cx1 or plate_y2 <= plate_y1:
            return
        crop = frame[plate_y1:plate_y2, cx1:cx2].copy()
        try:
            self._q.put_nowait((track_id, crop))
        except queue.Full:
            pass

    def get_best_plate(self, track_id: int) -> PlateCandidate | None:
        with self._lock:
            return self._candidates.get(track_id)

    def remove(self, track_id: int) -> None:
        with self._lock:
            self._candidates.pop(track_id, None)

    def _run(self) -> None:
        while True:
            track_id, crop = self._q.get()
            try:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < self._sharpness_threshold:
                    continue
                result = self._reader.read_plate_from_image_array(crop)
                if not result["plate_found"]:
                    continue
                plate_text = result["plate_text"]
                confidence = float(result["confidence"])
                if confidence < self._min_conf:
                    continue
                with self._lock:
                    candidate = self._candidates.get(track_id)
                    if candidate is None:
                        candidate = PlateCandidate(last_checked_at=time.time(), best_crop=crop)
                        self._candidates[track_id] = candidate
                    if plate_text not in candidate.votes:
                        candidate.votes[plate_text] = [0, 0.0]
                    candidate.votes[plate_text][0] += 1
                    if confidence > candidate.votes[plate_text][1]:
                        candidate.votes[plate_text][1] = confidence
                    if confidence > candidate.confidence:
                        candidate.best_crop = crop
                print(
                    f"ANPR live: track={track_id} skylt={plate_text} "
                    f"konf={confidence:.2f} röster={candidate.votes[plate_text][0]}"
                )
            except Exception as exc:
                print(f"PlateOCRWorker fel: {exc}")
            finally:
                self._q.task_done()


def get_event_type(line_name: str) -> str:
    if line_name == "parking_entry_line":
        return "parking_entry"

    if line_name == "parking_exit_line":
        return "parking_exit"

    return "road_passage"

def handle_passages(
    db: Database,
    frame,
    tracked_objects: dict[int, dict],
    line_counter: MultiLineCounter,
    plate_ocr_worker: "PlateOCRWorker | None" = None,
) -> None:
    for object_id, obj in tracked_objects.items():
        if obj.get("missing", 0) > 0:
            continue

        crossings = line_counter.check_crossings(
            object_id=object_id,
            previous_point=obj["previous_center"],
            current_point=obj["center"],
        )

        for crossing in crossings:
            line_name = crossing["line_name"]
            direction = crossing["direction"]
            event_type = get_event_type(line_name)
            final_category = classify_object(
                object_class=obj["class_name"],
                line_name=line_name,
            )

            # Hämta bästa skyltläsning från live-OCR-tråden.
            plate_text = None
            plate_confidence = 0.0
            if plate_ocr_worker is not None:
                candidate = plate_ocr_worker.get_best_plate(object_id)
                if candidate is not None and candidate.plate_text is not None:
                    plate_text = candidate.plate_text
                    plate_confidence = candidate.confidence

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
                plate_detected=plate_text is not None,
                plate_text=plate_text,
                plate_confidence=plate_confidence,
            )

            total = db.count_events()
            plate_info = f" | skylt={plate_text} ({plate_confidence:.2f})" if plate_text else ""
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
                f"{plate_info}"
            )

def _write_status(db_path: str, fps: float, stream: str) -> None:
    status_path = os.path.join(os.path.dirname(db_path), "status.json")
    try:
        with open(status_path, "w") as f:
            json.dump({
                "fps": round(fps, 1),
                "stream": stream,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }, f)
    except Exception:
        pass


def reconnect(rtsp_url: str, delay_seconds: int = 5) -> cv2.VideoCapture:
    print(f"Tappade strommen. Forsoker ateransluta om {delay_seconds} sekunder...")
    time.sleep(delay_seconds)
    return open_stream(rtsp_url)

def resize_for_display(frame):
    if DISPLAY_SCALE == 1:
        return frame

    height, width = frame.shape[:2]

    new_width = int(width * DISPLAY_SCALE)
    new_height = int(height * DISPLAY_SCALE)

    return cv2.resize(frame, (new_width, new_height))


def main() -> None:
    print("Startar CCounter med YOLO, tracking och flera linjer...")
    print(f"Modell: {YOLO_MODEL}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print(f"Detection zone: {DETECTION_ZONE}")
    print(f"Old count line: {COUNT_LINE}")
    print(f"Lines: {LINES}")

    if YOLO_MODEL.rstrip("/").endswith("_openvino_model"):
        model = OVDetector(YOLO_MODEL, device="GPU", conf=CONFIDENCE_THRESHOLD)
    else:
        import torch
        yolo_device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"YOLO device: {yolo_device}")
        model = YOLO(YOLO_MODEL)
        model.to(yolo_device)
    print("Modell laddad.")

    db = Database(DATABASE_PATH)

    tracker = CentroidTracker(
        max_distance=TRACKER_MAX_DISTANCE,
        max_missing_frames=TRACKER_MAX_MISSING_FRAMES,
    )

    line_counter = MultiLineCounter(LINES)
    plate_ocr_worker = PlateOCRWorker()

    cap = open_stream(RTSP_URL)
    db.log_stream_event("up")

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                db.log_stream_event("down")
                _write_status(DATABASE_PATH, fps=0.0, stream="down")
                cap.release()
                cap = None
                while cap is None:
                    print("Tappade strommen. Forsoker ateransluta om 5 sekunder...")
                    time.sleep(5)
                    try:
                        cap = open_stream(RTSP_URL)
                        db.log_stream_event("up")
                    except Exception as exc:
                        print(f"Ateranslutning misslyckades: {exc}")
                continue

            frame_count += 1

            if frame_count % PROCESS_EVERY_N_FRAMES != 0:
                continue

            detections = detect_vehicles(model, frame)
            old_ids = set(tracker.objects.keys())
            tracked_objects = tracker.update(detections)

            # Skicka fordonscrop till live-OCR-tråden
            vehicle_classes = {"car", "truck", "bus", "motorcycle"}
            for object_id, obj in tracked_objects.items():
                if obj.get("missing", 0) > 0:
                    continue
                if obj["class_name"] not in vehicle_classes:
                    continue
                plate_ocr_worker.submit(object_id, frame, obj["bbox"])

            # Rensa IDs som försvunnit ur trackern
            for removed_id in old_ids - set(tracked_objects.keys()):
                plate_ocr_worker.remove(removed_id)

            handle_passages(
                db=db,
                frame=frame,
                tracked_objects=tracked_objects,
                line_counter=line_counter,
                plate_ocr_worker=plate_ocr_worker,
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

                _write_status(DATABASE_PATH, fps=fps, stream="up")

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

                display_frame = resize_for_display(frame)
                cv2.imshow("CCounter - Tracking and multi-line counting", display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

    finally:
        try:
            db.log_stream_event("down")
        except Exception:
            pass
        cap.release()
        db.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()