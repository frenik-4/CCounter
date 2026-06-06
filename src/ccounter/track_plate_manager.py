import time
from dataclasses import dataclass, field

import cv2

from src.ccounter.plate_reader import PlateReader


@dataclass
class PlateCandidate:
    last_checked_at: float
    best_crop: object | None
    votes: dict = field(default_factory=dict)  # plate_text → [count, best_confidence]

    @property
    def plate_text(self) -> str | None:
        if not self.votes:
            return None
        return max(self.votes, key=lambda t: (self.votes[t][0], self.votes[t][1]))

    @property
    def confidence(self) -> float:
        text = self.plate_text
        if text is None:
            return 0.0
        return self.votes[text][1]

    @property
    def vote_count(self) -> int:
        text = self.plate_text
        if text is None:
            return 0
        return self.votes[text][0]


class TrackPlateManager:
    def __init__(
        self,
        plate_reader: PlateReader,
        min_confidence: float = 0.30,
        check_interval_seconds: float = 1.0,
        sharpness_threshold: float = 80.0,
    ):
        self.plate_reader = plate_reader
        self.min_confidence = min_confidence
        self.check_interval_seconds = check_interval_seconds
        self.sharpness_threshold = sharpness_threshold
        self.candidates: dict[int, PlateCandidate] = {}

    @staticmethod
    def is_sharp_enough(image, threshold: float) -> bool:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        return float(cv2.Laplacian(gray, cv2.CV_64F).var()) >= threshold

    def crop_object(self, frame, bbox: tuple[int, int, int, int]):
        """
        Crop the vehicle region most likely to contain a license plate.
        From this camera angle (side/rear quarter view), the plate appears
        in the middle vertical band of the bounding box (~25-75% from top).
        """
        frame_h, frame_w = frame.shape[:2]
        x1, y1, x2, y2 = bbox

        h = y2 - y1
        plate_y1 = y1 + int(h * 0.20)
        plate_y2 = y1 + int(h * 0.80)

        padding_x = int((x2 - x1) * 0.05)
        x1 = max(0, x1 - padding_x)
        x2 = min(frame_w, x2 + padding_x)
        plate_y1 = max(0, plate_y1)
        plate_y2 = min(frame_h, plate_y2)

        if x2 <= x1 or plate_y2 <= plate_y1:
            return None

        return frame[plate_y1:plate_y2, x1:x2].copy()

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

        if not self.is_sharp_enough(crop, self.sharpness_threshold):
            existing = self.candidates.get(track_id)
            if existing is not None:
                existing.last_checked_at = time.time()
            return

        result = self.plate_reader.read_plate_from_image_array(crop)
        now = time.time()

        existing = self.candidates.get(track_id)

        if existing is None:
            existing = PlateCandidate(last_checked_at=now, best_crop=crop)
            self.candidates[track_id] = existing
        else:
            existing.last_checked_at = now

        if not result["plate_found"]:
            return

        plate_text = result["plate_text"]
        confidence = float(result["confidence"])

        if confidence < self.min_confidence:
            return

        prev_confidence = existing.confidence

        if plate_text not in existing.votes:
            existing.votes[plate_text] = [0, 0.0]

        existing.votes[plate_text][0] += 1
        if confidence > existing.votes[plate_text][1]:
            existing.votes[plate_text][1] = confidence

        if confidence > prev_confidence:
            existing.best_crop = crop

        print(
            f"ANPR candidate: "
            f"track_id={track_id} "
            f"plate={plate_text} "
            f"confidence={confidence:.2f} "
            f"votes={existing.votes[plate_text][0]}"
        )

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
