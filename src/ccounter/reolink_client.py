"""
Delade hjälpfunktioner för att prata med trafikkamerans (Reolink RLC-811A)
admin-API. Används av camera_focus.py och camera_isp_tuning.py.
"""

import json
import ssl
import time
import urllib.request

import cv2
import numpy as np

from src.ccounter.config import CAM_PSWD, CAM_URL, CAM_USER

_SSL_CTX = ssl._create_unverified_context()


def _api_url(cmd: str) -> str:
    return f"{CAM_URL}/cgi-bin/api.cgi?cmd={cmd}"


def _retry_on_transient_error(func):
    # Kameran svarar ibland med ett tillfälligt fel (t.ex. rspCode -104
    # "unknown") om den hinner två anrop i följd för snabbt. Ett enda
    # kort omförsök löser det i praktiken.
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if (
            isinstance(result, list)
            and result
            and result[0].get("code") == 1
            and result[0].get("error", {}).get("rspCode") == -104
        ):
            time.sleep(2)
            result = func(*args, **kwargs)
        return result

    return wrapper


@_retry_on_transient_error
def _get(cmd: str, token: str | None = None, extra: str = "") -> dict:
    url = _api_url(cmd) + extra
    if token:
        url += f"&token={token}"
    with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


@_retry_on_transient_error
def _post(cmd: str, payload: list, token: str | None = None) -> dict:
    url = _api_url(cmd)
    if token:
        url += f"&token={token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def login() -> str:
    if not CAM_URL or not CAM_USER or not CAM_PSWD:
        raise RuntimeError("CAM/CAM_USER/CAM_PSWD saknas i .env")

    result = _post(
        "Login",
        [
            {
                "cmd": "Login",
                "action": 0,
                "param": {"User": {"userName": CAM_USER, "password": CAM_PSWD}},
            }
        ],
    )
    return result[0]["value"]["Token"]["name"]


def logout(token: str) -> None:
    try:
        _post("Logout", [{"cmd": "Logout", "action": 0, "param": {}}], token)
    except Exception:
        pass  # bästa-försök - kameran har ett tak för samtidiga sessioner,
        # så en misslyckad utloggning ska aldrig krascha ett körningsscript


def get_zoom_focus(token: str) -> dict:
    return _get("GetZoomFocus", token)[0]["value"]["ZoomFocus"]


def is_autofocus_disabled(token: str) -> bool:
    result = _post(
        "GetAutoFocus",
        [{"cmd": "GetAutoFocus", "action": 0, "param": {"channel": 0}}],
        token,
    )
    return bool(result[0]["value"]["AutoFocus"]["disable"])


def disable_autofocus(token: str) -> bool:
    result = _post(
        "SetAutoFocus",
        [{"cmd": "SetAutoFocus", "action": 0, "param": {"AutoFocus": {"channel": 0, "disable": 1}}}],
        token,
    )
    return result[0].get("code") == 0


def ensure_autofocus_disabled(token: str) -> bool:
    """
    Grundorsaken till timmar av felsökning 2026-09-28: kamerans egna
    kontinuerliga autofokus var PÅSLAGEN hela tiden och kämpade emot
    varje manuellt FocusPos-kommando - bekräftat genom att samma
    nominella fokusläge flimrade mellan skärpa ~13 och ~665 inom loppet
    av mindre än en sekund. Måste vara avstängd för att manuell
    fokusjustering ska vara meningsfull överhuvudtaget.

    Returnerar True om AF var/blev avstängd, False om det misslyckades
    (t.ex. tillfälligt API-fel) - anropare bör då avstå från att lita på
    skärpemätningar den körningen.
    """
    if is_autofocus_disabled(token):
        return True
    return disable_autofocus(token) and is_autofocus_disabled(token)


def set_focus_pos(token: str, pos: int) -> bool:
    result = _post(
        "StartZoomFocus",
        [
            {
                "cmd": "StartZoomFocus",
                "action": 0,
                "param": {"ZoomFocus": {"channel": 0, "op": "FocusPos", "pos": pos}},
            }
        ],
        token,
    )
    return result[0].get("code") == 0


def get_isp(token: str) -> dict:
    return _get("GetIsp", token, extra="&channel=0")[0]["value"]["Isp"]


def set_isp(token: str, fields: dict) -> bool:
    # Kameran kräver att HELA Isp-objektet skickas - att bara skicka det
    # ändrade fältet ger "param error" för vissa fält (t.ex. backLight),
    # även om det råkar fungera för andra (t.ex. exposure). Läs alltid
    # aktuellt läge först och slå ihop, så det fungerar konsekvent.
    current = get_isp(token)
    payload_fields = {**current, **fields, "channel": 0}
    result = _post(
        "SetIsp",
        [{"cmd": "SetIsp", "action": 0, "param": {"Isp": payload_fields}}],
        token,
    )
    return result[0].get("code") == 0


def get_snapshot(token: str):
    last_error = None

    for attempt in range(2):
        try:
            url = _api_url("Snap") + f"&channel=0&rs={int(time.time() * 1000)}&token={token}"
            with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
                data = resp.read()

            if data[:2] == b"\xff\xd8":  # JPEG magic bytes = giltig bild
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return img
                last_error = "cv2.imdecode gav None trots giltiga JPEG-headers"
            else:
                last_error = f"inget JPEG-svar: {data[:200]!r}"
        except Exception as exc:
            # Nätverksfel (timeout, connection reset) ska också ge samma
            # omförsök som ett tillfälligt API-fel, inte kasta direkt.
            last_error = str(exc)

        if attempt == 0:
            time.sleep(2)

    raise RuntimeError(f"Snap misslyckades: {last_error}")


def is_ir_mode(img) -> bool:
    b, g, r = (channel.astype(np.int16) for channel in cv2.split(img))
    diff = float(
        np.mean(np.abs(b - g)) + np.mean(np.abs(g - r)) + np.mean(np.abs(b - r))
    )
    return diff < 6.0


def sharpness_score(img, region: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = region
    h, w = img.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    crop = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def measure_sharpness(
    token: str,
    region: tuple[int, int, int, int],
    max_samples: int = 6,
    spacing_seconds: float = 1.5,
    stability_ratio: float = 0.85,
) -> float:
    """
    Ett enda foto direkt efter en fokusflytt är opålitligt - inte bara pga
    brus (vind i löv/grenar), utan för att objektivets motor kan behöva
    flera sekunder att verkligen färdigställa sig efter flera
    riktningsbyten i rad. En fast väntetid visade sig gissa fel: 1.5s var
    för kort, men samma läge kunde ändå ge ett dåligt värde efter 5s om
    föregående körning nyss gjort flera snabba riktningsbyten (bekräftat
    genom felsökning 2026-09-28 - se camera_focus.py:s docstring).

    Istället för att gissa en konstant: ta prover med paus emellan och
    sluta så fort TVÅ i följd är inbördes stabila (inom stability_ratio
    av varandra) - det är det starkaste tecknet på att motorn verkligen
    har satt sig. Om det aldrig stabiliserar sig inom max_samples
    (ovanligt - tyder på ett djupare problem, t.ex. att autofokus ändå
    är påslagen) returneras sista provet ändå, så körningen inte hänger
    sig för evigt.
    """
    previous = None
    last = 0.0

    for i in range(max_samples):
        img = get_snapshot(token)
        last = sharpness_score(img, region)

        if previous is not None and previous > 0:
            ratio = min(last, previous) / max(last, previous)
            if ratio >= stability_ratio:
                return last

        previous = last
        if i < max_samples - 1:
            time.sleep(spacing_seconds)

    return last


def noise_score(img, region: tuple[int, int, int, int]) -> float:
    """
    Immerkærs brusuppskattning - mäter okorrelerat sensorbrus specifikt,
    till skillnad från Laplacian-variansen (sharpness_score) som INTE kan
    skilja på riktig skärpa och brus (båda ger hög varians). Upptäckte att
    nr3d=0 (avstängd 3D-brusreducering) gav en helt korngrynig bild som
    sharpness_score felaktigt bedömde som "mycket skarpare".
    """
    x1, y1, x2, y2 = region
    h, w = img.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    crop = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float64)
    height, width = gray.shape
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]])
    conv = cv2.filter2D(gray, -1, kernel)
    return float(
        np.sum(np.abs(conv)) * np.sqrt(0.5 * np.pi) / (6 * (width - 2) * (height - 2))
    )


def exposure_health(img) -> tuple[bool, str]:
    """
    Grov sanity-check av EXPONERINGEN (inte skärpan) över hela bilden.
    Upptäcker t.ex. att IR-ljuset studsar mot närliggande buskage och
    bränner ut halva bilden - det missades av skärpemåttet ensamt när
    exposure=Anti-Smearing testades manuellt 2026-09-27.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    total = gray.size
    blown = np.count_nonzero(gray >= 250) / total
    crushed = np.count_nonzero(gray <= 3) / total

    if blown > 0.12:
        return False, f"{blown * 100:.1f}% överexponerade pixlar"
    if crushed > 0.92:
        return False, f"{crushed * 100:.1f}% helt svarta pixlar"

    return True, "ok"
