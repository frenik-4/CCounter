"""
YOLOv8-inferens direkt via OpenVINO — kringgår ultralytics' CUDA-validering
så att Intel iGPU (UHD 630) kan användas som inferencenhet.
"""

import cv2
import numpy as np
import openvino as ov
import yaml
from pathlib import Path


def _load_names(model_dir: Path) -> dict[int, str]:
    meta = model_dir / "metadata.yaml"
    if meta.exists():
        with open(meta) as f:
            data = yaml.safe_load(f)
        return {int(k): v for k, v in data.get("names", {}).items()}
    return {}


def _letterbox(img: np.ndarray, target: tuple[int, int] = (640, 640)):
    oh, ow = img.shape[:2]
    ratio = min(target[0] / oh, target[1] / ow)
    new_w, new_h = int(round(ow * ratio)), int(round(oh * ratio))
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    dw = (target[1] - new_w) / 2
    dh = (target[0] - new_h) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right  = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, ratio, dw, dh


class OVDetector:
    """
    Laddar en YOLOv8 OpenVINO-modell och kör inferens på angiven enhet
    (t.ex. 'GPU' för Intel UHD 630 eller 'CPU' för OpenVINO-optimerad CPU).
    """

    def __init__(self, model_dir: str, device: str = "GPU", conf: float = 0.25, iou: float = 0.45):
        path = Path(model_dir)
        xml = next(path.glob("*.xml"))

        core = ov.Core()
        ov_model = core.read_model(str(xml))
        print(f"OVDetector: kompilerar på {device}...")
        compiled = core.compile_model(ov_model, device)
        self._req = compiled.create_infer_request()
        self.names = _load_names(path)
        self.conf = conf
        self.iou = iou
        print(f"OVDetector: klar ({device})")

    def __call__(self, frame: np.ndarray, conf: float | None = None) -> list[dict]:
        threshold = conf if conf is not None else self.conf
        orig_h, orig_w = frame.shape[:2]

        # --- Förbehandling ---
        blob, ratio, dw, dh = _letterbox(frame)
        blob = cv2.cvtColor(blob, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]  # (1, 3, 640, 640)

        # --- Inferens ---
        self._req.infer({0: blob})
        raw = self._req.get_output_tensor(0).data  # (1, 84, 8400)
        preds = raw[0].T  # (8400, 84)

        # --- Avkodning ---
        boxes_raw = preds[:, :4]   # cx, cy, w, h i 640×640-rymd
        class_scores = preds[:, 4:]  # (8400, 80)

        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]

        keep = confidences >= threshold
        if not keep.any():
            return []

        boxes_raw = boxes_raw[keep]
        confidences = confidences[keep]
        class_ids = class_ids[keep]

        # cx cy w h → x1 y1 x2 y2
        x1 = boxes_raw[:, 0] - boxes_raw[:, 2] / 2
        y1 = boxes_raw[:, 1] - boxes_raw[:, 3] / 2
        x2 = boxes_raw[:, 0] + boxes_raw[:, 2] / 2
        y2 = boxes_raw[:, 1] + boxes_raw[:, 3] / 2

        # Skala tillbaka till originalstorlek (ta bort letterbox-padding)
        x1 = np.clip((x1 - dw) / ratio, 0, orig_w).astype(int)
        y1 = np.clip((y1 - dh) / ratio, 0, orig_h).astype(int)
        x2 = np.clip((x2 - dw) / ratio, 0, orig_w).astype(int)
        y2 = np.clip((y2 - dh) / ratio, 0, orig_h).astype(int)

        # --- NMS per klass ---
        detections = []
        for cls_id in np.unique(class_ids):
            m = class_ids == cls_id
            xywh = np.stack([x1[m], y1[m], x2[m] - x1[m], y2[m] - y1[m]], axis=1)
            idxs = cv2.dnn.NMSBoxes(xywh.tolist(), confidences[m].tolist(), 0.0, self.iou)
            if len(idxs) == 0:
                continue
            for i in idxs.flatten():
                bx1, by1, bx2, by2 = x1[m][i], y1[m][i], x2[m][i], y2[m][i]
                detections.append({
                    "class_id":   int(cls_id),
                    "class_name": self.names.get(int(cls_id), str(cls_id)),
                    "confidence": float(confidences[m][i]),
                    "bbox":       (int(bx1), int(by1), int(bx2), int(by2)),
                    "center":     (int((bx1 + bx2) // 2), int((by1 + by2) // 2)),
                })

        return detections
