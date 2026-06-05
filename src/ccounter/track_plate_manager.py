import time
from dataclasses import dataclass

import cv2

from src.ccounter.plate_reader import PlateReader


@dataclass
class PlateCandidate:
    plate_text: str | None
    confidence: float
    last_checked_at: float
    best_crop: object | None


class TrackPlateManager:
    def __init__(
        self,
        plate_reader: PlateReader,
        min_confidence: float = 0.30,
        check_interval_seconds: float = 1.0,
    ):
        self.plate_reader = plate_reader
        self.min_confidence = min_confidence
        self.check_interval_seconds = check_interval_seconds
        self.candidates: dict[int, PlateCandidate] = {}

    def crop_object(self, frame, bbox: tuple[int, int, int, int]):
        height, width = frame.shape[:2]

        x1, y1, x2, y2 = bbox

        padding_x = int((x2 - x1) * 0.10)
        padding_y = int((y2 - y1) * 0.10)

        x1 = max(0, x1 - padding_x)
        y1 = max(0, y1 - padding_y)
        x2 = min(width, x2 + padding_x)
        y2 = min(height, y2 + padding_y)

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[y1:y2, x1:x2].copy()

    def should_check_track(self, track_id: int) -> bool:
        candidate = self.candidates.get(track_id)

        if candidate is None:
            return True

        now = time.time()
        return (now - candidate.last_checked_at) >= self.check_interval_seconds

    def update_track(
        self,
        track_id: int,
        frame,
        bbox: tuple[int, int, int, int],
    ) -> None:
        if not self.should_check_track(track_id):
            return

        crop = self.crop_object(frame, bbox)

        if crop is None:
            return

        result = self.plate_reader.read_plate_from_image_array(crop)
        now = time.time()

        existing = self.candidates.get(track_id)

        if not result["plate_found"]:
            if existing is None:
                self.candidates[track_id] = PlateCandidate(
                    plate_text=None,
                    confidence=0.0,
                    last_checked_at=now,
                    best_crop=crop,
                )
            else:
                existing.last_checked_at = now

            return

        plate_text = result["plate_text"]
        confidence = float(result["confidence"])

        if confidence < self.min_confidence:
            if existing is None:
                self.candidates[track_id] = PlateCandidate(
                    plate_text=None,
                    confidence=confidence,
                    last_checked_at=now,
                    best_crop=crop,
                )
            else:
                existing.last_checked_at = now

            return

        if existing is None or confidence > existing.confidence:
            self.candidates[track_id] = PlateCandidate(
                plate_text=plate_text,
                confidence=confidence,
                last_checked_at=now,
                best_crop=crop,
            )

            print(
                f"ANPR candidate updated: "
                f"track_id={track_id} plate={plate_text} confidence={confidence:.2f}"
            )
        else:
            existing.last_checked_at = now

    def get_best_plate(self, track_id: int) -> PlateCandidate | None:
        return self.candidates.get(track_id)

    def save_best_crop(
        self,
        track_id: int,
        output_path: str,
    ) -> bool:
        candidate = self.candidates.get(track_id)

        if candidate is None:
            return False

        if candidate.best_crop is None:
            return False

        cv2.imwrite(output_path, candidate.best_crop)
        return True

    def remove_track(self, track_id: int) -> None:
        self.candidates.pop(track_id, None)