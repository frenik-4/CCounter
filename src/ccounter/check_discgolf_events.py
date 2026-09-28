"""
Hämtar kommande event från Ale Disc Golf Centers publika iCal-flöde och
lägger in dem som day_comments, så trafikstatistik kan jämföras mot
eventdagar. Körs veckovis via cron.
"""

import re
import urllib.request
from datetime import date, timedelta

from src.ccounter.config import DATABASE_PATH
from src.ccounter.database import Database

ICAL_URL = "https://www.discgolfcenter.se/discgolf-events/list/?ical=1"
SOURCE = "discgolfcenter.se"


def _parse_ical_date(value: str) -> date:
    # DTSTART;VALUE=DATE:20261024 eller DTSTART;TZID=Europe/Stockholm:20261024T090000
    digits = re.search(r"(\d{8})", value)
    return date(int(digits.group(1)[0:4]), int(digits.group(1)[4:6]), int(digits.group(1)[6:8]))


def fetch_events() -> list[dict]:
    req = urllib.request.Request(ICAL_URL, headers={"User-Agent": "CCounter/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    # Ical-radvikning: fortsättningsrader börjar med ett mellanslag.
    raw = raw.replace("\r\n ", "").replace("\n ", "")
    lines = raw.splitlines()

    events = []
    current: dict = {}
    in_event = False

    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
            continue
        if line == "END:VEVENT":
            in_event = False
            if "summary" in current and "dtstart" in current:
                events.append(current)
            continue
        if not in_event:
            continue

        if line.startswith("SUMMARY:"):
            current["summary"] = line[len("SUMMARY:") :].strip()
        elif line.startswith("DTSTART"):
            key, _, value = line.partition(":")
            current["dtstart"] = _parse_ical_date(value)
        elif line.startswith("DTEND"):
            key, _, value = line.partition(":")
            current["dtend"] = _parse_ical_date(value)

    return events


def main() -> None:
    db = Database(DATABASE_PATH)

    try:
        events = fetch_events()
    except Exception as exc:
        print(f"Kunde inte hämta eventkalendern: {exc}")
        db.close()
        return

    added = 0
    for ev in events:
        start = ev["dtstart"]
        # DTEND i iCal är exklusiv (dagen efter sista eventdagen).
        end = ev.get("dtend", start + timedelta(days=1)) - timedelta(days=1)
        if end < start:
            end = start

        d = start
        while d <= end:
            db.add_day_comment(
                d.isoformat(),
                f"Discgolf: {ev['summary']} (Ale Disc Golf Center)",
                source=SOURCE,
            )
            added += 1
            d += timedelta(days=1)

    print(f"Klar. {len(events)} event hittade i kalendern, {added} dagsrader kontrollerade/tillagda.")
    db.close()


if __name__ == "__main__":
    main()
