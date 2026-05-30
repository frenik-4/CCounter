import time

import cv2

from src.ccounter.config import RTSP_URL, SHOW_WINDOW


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


def main() -> None:
    cap = open_stream(RTSP_URL)

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("Ingen bild från kameran. Försöker igen...")
            time.sleep(1)
            continue

        frame_count += 1

        if frame_count % 30 == 0:
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            print(f"Läser bild från kameran. FPS cirka: {fps:.1f}")

        if SHOW_WINDOW:
            cv2.imshow("CCounter - RTSP test", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()