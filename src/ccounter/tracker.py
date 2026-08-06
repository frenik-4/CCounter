import math

# Hur mycket bbox-diagonalen får skala upp tillåtet matchningsavstånd.
# Stora/höga fordon nära kameran har en boundingbox som svänger kraftigt i
# storlek mellan bildrutor (t.ex. när toppen av ett högt fordon går in/ut ur
# bild), vilket flyttar centroiden mer än ett normalt fordon utan att det
# faktiskt är ett nytt objekt. Ett fast max_distance tappar då spårningen
# och registrerar aldrig en fullständig linjekorsning för sådana fordon.
BBOX_DISTANCE_FACTOR = 0.6


def _bbox_diagonal(bbox: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = bbox
    return math.hypot(x2 - x1, y2 - y1)


class CentroidTracker:
    def __init__(self, max_distance: int = 120, max_missing_frames: int = 25):
        self.next_object_id = 1
        self.objects: dict[int, dict] = {}

        self.max_distance = max_distance
        self.max_missing_frames = max_missing_frames

    def update(self, detections: list[dict]) -> dict[int, dict]:
        if len(detections) == 0:
            self._mark_all_missing()
            return self.objects

        unmatched_detections = set(range(len(detections)))
        unmatched_objects = set(self.objects.keys())

        matches = []

        for object_id, obj in list(self.objects.items()):
            best_detection_index = None
            best_distance = float("inf")
            best_allowed_distance = self.max_distance

            ox, oy = obj["center"]
            obj_diagonal = _bbox_diagonal(obj["bbox"])

            for detection_index in list(unmatched_detections):
                detection = detections[detection_index]
                dx, dy = detection["center"]
                distance = math.hypot(dx - ox, dy - oy)

                if distance < best_distance:
                    det_diagonal = _bbox_diagonal(detection["bbox"])
                    allowed_distance = max(
                        self.max_distance,
                        BBOX_DISTANCE_FACTOR * max(obj_diagonal, det_diagonal),
                    )
                    best_distance = distance
                    best_detection_index = detection_index
                    best_allowed_distance = allowed_distance

            if best_detection_index is not None and best_distance <= best_allowed_distance:
                matches.append((object_id, best_detection_index))
                unmatched_detections.remove(best_detection_index)
                unmatched_objects.discard(object_id)

        for object_id, detection_index in matches:
            detection = detections[detection_index]
            previous_center = self.objects[object_id]["center"]

            self.objects[object_id].update(
                {
                    "bbox": detection["bbox"],
                    "previous_center": previous_center,
                    "center": detection["center"],
                    "class_id": detection["class_id"],
                    "class_name": detection["class_name"],
                    "confidence": detection["confidence"],
                    "missing": 0,
                }
            )

        for detection_index in unmatched_detections:
            detection = detections[detection_index]

            self.objects[self.next_object_id] = {
                "bbox": detection["bbox"],
                "previous_center": detection["center"],
                "center": detection["center"],
                "class_id": detection["class_id"],
                "class_name": detection["class_name"],
                "confidence": detection["confidence"],
                "missing": 0,
            }

            self.next_object_id += 1

        for object_id in list(unmatched_objects):
            self.objects[object_id]["missing"] += 1

            if self.objects[object_id]["missing"] > self.max_missing_frames:
                del self.objects[object_id]

        return self.objects

    def _mark_all_missing(self) -> None:
        for object_id in list(self.objects.keys()):
            self.objects[object_id]["missing"] += 1

            if self.objects[object_id]["missing"] > self.max_missing_frames:
                del self.objects[object_id]