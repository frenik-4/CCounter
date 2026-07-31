"""
Dagligt underhåll av snapshot-mappen.

- Tar bort _anpr*.jpg-filer äldre än 7 dagar
- Arkiverar (zippar) fullbilder vecka för vecka (måndag–söndag)
  Zip-filnamn: snapshots_2026-06-01_2026-06-07.zip
  Arkiv hamnar i: data/snapshots/archives/

Användning:
    python -m src.ccounter.maintenance
"""

import zipfile
from datetime import date, timedelta
from pathlib import Path

from src.ccounter.config import ARCHIVE_MAX_WEEKS, SNAPSHOT_DIR

SNAPSHOT_PATH = Path(SNAPSHOT_DIR)
ARCHIVE_DIR = SNAPSHOT_PATH / "archives"
ANPR_MAX_AGE_DAYS = 7


def _file_date(path: Path) -> date | None:
    name = path.name
    try:
        return date(int(name[:4]), int(name[4:6]), int(name[6:8]))
    except (ValueError, IndexError):
        return None


def delete_old_anpr_crops() -> int:
    cutoff = date.today() - timedelta(days=ANPR_MAX_AGE_DAYS)
    deleted = 0
    for f in SNAPSHOT_PATH.glob("*_anpr*.jpg"):
        d = _file_date(f)
        if d and d < cutoff:
            f.unlink()
            deleted += 1
    return deleted


def archive_completed_weeks() -> list[str]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())

    full_images = [f for f in SNAPSHOT_PATH.glob("*.jpg") if "_anpr" not in f.name]

    weeks: dict[date, list[Path]] = {}
    for f in full_images:
        d = _file_date(f)
        if d is None:
            continue
        monday = d - timedelta(days=d.weekday())
        if monday >= current_week_start:
            continue
        weeks.setdefault(monday, []).append(f)

    archived = []
    for monday, files in sorted(weeks.items()):
        sunday = monday + timedelta(days=6)
        zip_name = f"snapshots_{monday.isoformat()}_{sunday.isoformat()}.zip"
        zip_path = ARCHIVE_DIR / zip_name

        if zip_path.exists():
            continue

        print(f"Arkiverar {monday} - {sunday}: {len(files)} filer...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(files):
                zf.write(f, f.name)

        for f in files:
            f.unlink()

        archived.append(zip_name)

    return archived


def prune_old_archives() -> int:
    """Raderar veckoarkiv äldre än ARCHIVE_MAX_WEEKS. 0 = behåll allt."""
    if ARCHIVE_MAX_WEEKS <= 0:
        return 0

    cutoff = date.today() - timedelta(weeks=ARCHIVE_MAX_WEEKS)
    deleted = 0
    for zip_path in ARCHIVE_DIR.glob("snapshots_*_*.zip"):
        # Filnamn: snapshots_YYYY-MM-DD_YYYY-MM-DD.zip — jämför veckans slutdatum.
        try:
            end = date.fromisoformat(zip_path.stem.split("_")[2])
        except (ValueError, IndexError):
            continue
        if end < cutoff:
            zip_path.unlink()
            deleted += 1
    return deleted


def main() -> None:
    print(f"Snapshot-mapp: {SNAPSHOT_PATH}")

    deleted = delete_old_anpr_crops()
    print(f"Borttagna ANPR-crops (>{ANPR_MAX_AGE_DAYS} dagar): {deleted}")

    archived = archive_completed_weeks()
    if archived:
        for z in archived:
            print(f"Arkiverad: {z}")
    else:
        print("Inga veckor att arkivera.")

    pruned = prune_old_archives()
    print(f"Borttagna veckoarkiv (>{ARCHIVE_MAX_WEEKS} veckor): {pruned}")


if __name__ == "__main__":
    main()
