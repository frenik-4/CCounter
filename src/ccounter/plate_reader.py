import re
from pathlib import Path

import cv2
import easyocr


# Svenska:  ABC123 / ABC12D      (3 bokstäver + 2 siffror + siffra/bokstav)
# Norska:   AB12345             (2 bokstäver + 5 siffror)
# Danska:   AB12345             (samma som norska)
# Polska:   WA12345 / WA1234A   (2 bokstäver + 4–5 alfanumeriska)
# Tyska:    ABCD1234            (1–3 bokstäver stad + 1–2 bokstäver + 1–4 siffror,
#                                totalt minst 6 tecken — fångas av post-filter nedan)
PLATE_PATTERNS = [
    re.compile(r"[A-Z]{3}[0-9]{2}[A-Z0-9]"),        # Sverige
    re.compile(r"[A-Z]{2}[0-9]{5}"),                 # Norge / Danmark
    re.compile(r"[A-Z]{2}[A-Z0-9]{4,5}"),            # Polen
    re.compile(r"[A-Z]{1,3}[A-Z]{1,2}[0-9]{1,4}"),  # Tyskland (brett — röstning filtrerar brus)
]
PLATE_MIN_LENGTH = 6  # kasta träffar kortare än detta (skyddar mot tyska korta falska positiva)
PLATE_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class PlateReader:
    def __init__(self, gpu: bool = False):
        print(f"Loading EasyOCR (gpu={gpu})...")
        self.reader = easyocr.Reader(["en"], gpu=gpu)
        print("EasyOCR loaded.")

    def clean_text(self, text: str) -> str:
        text = text.upper()
        text = text.replace(" ", "")
        text = text.replace("-", "")
        text = text.replace(".", "")
        text = text.replace(":", "")
        text = text.replace("_", "")
        text = text.replace("/", "")
        text = text.replace("\\", "")
        return text

    def extract_plate_candidates(self, text: str) -> list[str]:
        cleaned = self.clean_text(text)
        all_matches = set()
        for pattern in PLATE_PATTERNS:
            for match in pattern.findall(cleaned):
                if len(match) >= PLATE_MIN_LENGTH:
                    all_matches.add(match)
        # Ta bort matchningar som är substring av en längre matchning
        # (t.ex. BCD123 när MABCD123 också finns, eller AB1234 när AB12345 finns)
        filtered = [m for m in all_matches if not any(
            m in other and len(other) > len(m) for other in all_matches
        )]
        return sorted(filtered, key=len, reverse=True)

    def preprocess_image(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        height, width = gray.shape[:2]

        if width < 1000:
            scale = 1000 / width
            gray = cv2.resize(
                gray,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        blurred = cv2.GaussianBlur(gray, (0, 0), 3)
        gray = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

        return gray

    def read_plate_from_image_array(self, image) -> dict:
        if image is None:
            return {
                "plate_found": False,
                "plate_text": None,
                "confidence": 0.0,
                "raw_results": [],
                "error": "Image is None",
            }

        if image.size == 0:
            return {
                "plate_found": False,
                "plate_text": None,
                "confidence": 0.0,
                "raw_results": [],
                "error": "Image is empty",
            }

        processed = self.preprocess_image(image)
        results = self.reader.readtext(processed, allowlist=PLATE_ALLOWLIST)

        best_plate = None
        best_confidence = 0.0
        raw_results = []

        for _bbox, text, confidence in results:
            raw_results.append(
                {
                    "text": text,
                    "confidence": float(confidence),
                }
            )

            candidates = self.extract_plate_candidates(text)

            for candidate in candidates:
                if confidence > best_confidence:
                    best_plate = candidate
                    best_confidence = float(confidence)

        # EasyOCR delar ibland upp skylten i flera segment (t.ex. "MRP" + "281").
        # Försök kombinera alla segment och sök mönstret i den sammansatta texten.
        if best_plate is None and len(raw_results) > 1:
            combined = "".join(self.clean_text(r["text"]) for r in raw_results)
            candidates = self.extract_plate_candidates(combined)
            if candidates:
                avg_conf = sum(r["confidence"] for r in raw_results) / len(raw_results)
                best_plate = candidates[0]
                best_confidence = avg_conf

        return {
            "plate_found": best_plate is not None,
            "plate_text": best_plate,
            "confidence": best_confidence,
            "raw_results": raw_results,
            "error": None,
        }

    def read_plate_from_image(self, image_path: str | Path) -> dict:
        image_path = Path(image_path)
        image = cv2.imread(str(image_path))

        if image is None:
            return {
                "plate_found": False,
                "plate_text": None,
                "confidence": 0.0,
                "raw_results": [],
                "error": f"Could not read image: {image_path}",
            }

        result = self.read_plate_from_image_array(image)
        result["image_path"] = str(image_path)

        return result
