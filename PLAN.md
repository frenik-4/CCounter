# CCounter Plan

## Goal

CCounter is a local traffic monitoring app.

It should:

- read an RTSP camera stream
- detect vehicles, people, bicycles and animals
- track objects over time
- count crossings over configurable lines
- separate normal road traffic from parking traffic
- store detailed data locally
- export only safe aggregated statistics to an external website
- support local-only license plate recognition for filtering and grouping

## Privacy rules

Detailed data stays local.

Local database may include:

- events
- snapshots
- track IDs
- object classes
- confidence values
- local license plate data
- local known-plate groups

External/public exports must not include:

- license plates
- snapshots
- raw event rows
- personal details
- camera stream access

## Current status

Done:

- basic project structure
- `.env` configuration
- GitHub workflow with helper script
- RTSP stream test
- YOLO detection
- display scaling with `DISPLAY_SCALE`
- detection zone filtering
- SQLite event database
- multiple line configuration
- multi-line counter foundation
- main road line
- parking entry line (tuned to road/gravel boundary)
- live multi-line event counting tested
- event snapshots saved locally
- local known plate classification foundation
- object category classifier
- safe public stats export (SQL-aggregerad, inklusive individuella events per timme utan privat data)
- static public dashboard
- SFTP publishing to external web hosting
- automatic public publishing foundation
- architecture documentation
- Reolink RLC-811A camera installed and tested, 5x optisk zoom konfigurerad
- ANPR med EasyOCR (asynkron, snapshot-baserad)
- `anpr_worker.py` — fristående worker som bearbetar sparade snapshots
- ren `_anpr.jpg`-crop (full 4K, inga overlays) sparas vid varje korsning
- `anpr_attempted`-flagga i databasen — förhindrar att events bearbetas om
- schemalagd ANPR-worker körs automatiskt varje hel timme via Claude Scheduled Tasks
- realtids-ANPR borttagen från `app.py` (gick åt för mycket CPU)
- `database.py`: `update_event_plate()`, `get_unprocessed_anpr_events()`, `mark_anpr_attempted()`
- CLAHE + unsharp mask preprocessing, EasyOCR allowlist `A-Z0-9`
- blur detection via Laplacian variance
- `PROCESS_EVERY_N_FRAMES` implemented for CPU savings
- publik dashboard: riktningsstatistik (Söderut/Norrut), korrigerade A→B/B→A-riktningar
- fotgängare filtreras bort från publik export
- bugfixes: handle_passages scope, reconnect loop, export memory usage

## Current camera

Current camera:

- Reolink RLC-811A
- Ethernet/PoE
- 3840×2160 (4K), 25 fps
- RTSP stream working
- DISPLAY_SCALE=0.4

Previous temporary camera:

- Deltaco SH-IPC17
- RTSP worked but image quality was unstable
- codec could not be changed
- no longer the target camera

## Planned server

Planned 24/7 server:

- Dell Precision 3430 / Optiplex-class machine
- Intel i5-8500
- 16 GB RAM
- 256 GB SSD
- Linux

Purpose:

- run CCounter 24/7
- store local SQLite database
- store local snapshots
- run scheduled public exports
- push public statistics to external web hosting

## Current public website

Public dashboard:

- hosted externally
- receives only safe aggregated statistics
- current upload method: SFTP
- public files:
  - `index.html`
  - `stats.json`

Public dashboard currently shows:

- selectable day
- totals for selected day (exkl. fotgängare och parkering)
- kategorier
- riktningsstatistik: Söderut (A→B) och Norrut (B→A)
- timmar med individuella events (tid, typ, kategori, riktning — inga reg.nr)
- dygnsgraf

Public dashboard must not show:

- license plates
- snapshots
- raw database rows
- private notes
- known-plate labels

## Next steps

1. Verifiera zon och linjer med verklig trafik — justera vid behov.
2. ANPR-träffsäkerhet — utvärdera efter några dagars körning med ny kameravinkel och `_anpr.jpg`-crops.
3. Eventuellt sänka `PLATE_READER_SHARPNESS_THRESHOLD` (nu 80.0) om för många crops kastas.
4. Lägg till parkeringsutfarts-linje om separering av in/ut önskas.
5. Förbättra klassificering av events.
6. GPU för ANPR (`PLATE_READER_GPU=true`) när RTX 3050 eller liknande installerats på servern.
7. Lägg till databas-summeringskommandon.
8. Förbered Linux 24/7-server (systemd-tjänst, automatisk start).
9. Flytta projektet från Windows-dev till Linux-server.
10. Konfigurera publik export/publicering på servern.
11. Lägg till övervakning/loggning för 24/7-drift.

## Current ANPR status

Arkitektur (asynkron, snapshot-baserad):

- `app.py` sparar en ren `_anpr.jpg`-crop (full 4K, inga overlays) vid varje korsning.
- `anpr_worker.py` körs automatiskt varje hel timme via Claude Scheduled Tasks.
- Workern bearbetar bara events med `anpr_attempted=0` — processas aldrig om.
- Försök 1: ladda `_anpr.jpg`-crop (ny metod, inga overlays).
- Försök 2: croppa fordon ur full annoterad snapshot med bbox från DB (retroaktiv).
- Försök 3: hela snapshot som sista utväg.
- `PlateReader`: CLAHE + unsharp mask, EasyOCR `A-Z0-9` allowlist, blur detection.
- GPU disabled by default (`PLATE_READER_GPU=false`).

Träffsäkerhet:

- Gamla events (bred kameravinkel): ~14% (29/200) träff.
- Nya events (5x zoom, ren crop): ännu inte utvärderat.
- `PLATE_MIN_CONFIDENCE=0.30`, `PLATE_READER_SHARPNESS_THRESHOLD=80.0`.

## Local known-plate handling

Planned usage:

- known own vehicles
- neighbor vehicles
- delivery vehicles
- service vehicles
- vehicles to exclude from public statistics
- vehicles to count separately

Rules:

- known plate list is local only
- known plate labels are local only
- public dashboard must not include plate text or labels
- public dashboard may include aggregated counts only

## Important design decisions

- SQLite is the local source of truth.
- External website should only receive exported summaries.
- License plates stay local only.
- Snapshots stay local only.
- The external website must never access the camera stream.
- The external website must never read the private event database directly.
- Public exports must be generated from filtered/safe data only.
- Parking traffic is stored locally but hidden from the public dashboard.

## Current .env — key values

```
DETECTION_ZONE=0,759;3204,759;3204,2089;0,2089
LINES=main_count_line:2189,759,2189,1650;parking_entry_line:1028,2076,3204,1322
DISPLAY_SCALE=0.4
PROCESS_EVERY_N_FRAMES=3
CONFIDENCE_THRESHOLD=0.40
TRACKER_MAX_DISTANCE=400
TRACKER_MAX_MISSING_FRAMES=25
PLATE_RECOGNITION_ENABLED=true
PLATE_MIN_CONFIDENCE=0.30
PLATE_READER_GPU=false
PLATE_READER_SHARPNESS_THRESHOLD=80.0
SAVE_SNAPSHOTS=true
```

Kamera: Reolink RLC-811A, 5x optisk zoom, monterad mot vägen.
Räknelinjen (main_count_line) är lodrät, passerar vägen precis vid grusgränsen.
Parkeringslinjen (parking_entry_line) är diagonal längs väg/grusgränsen.

## Useful commands

Start app:

```powershell
.\start_ccounter.bat
```

Kör ANPR-worker manuellt:

```powershell
.\.venv\Scripts\python.exe -m src.ccounter.anpr_worker
```

Visa senaste events:

```powershell
.\.venv\Scripts\python.exe -m src.ccounter.show_events
```

Exportera publik JSON:

```powershell
.\.venv\Scripts\python.exe -m src.ccounter.export_public_json
```

Publicera webbsida:

```powershell
.\.venv\Scripts\python.exe -m src.ccounter.publish_public_site
```

Kör tester:

```powershell
.\.venv\Scripts\python.exe -m pytest src/ccounter/ -q
```

Syntaxkoll:

```powershell
.\.venv\Scripts\python.exe -m py_compile src\ccounter\app.py
```

Commit:

```powershell
.\git-save.ps1 -Message "Your message here"
```

## Files and folders

Important source files:

```text
src/ccounter/app.py
src/ccounter/config.py
src/ccounter/database.py
src/ccounter/tracker.py
src/ccounter/counter.py
src/ccounter/classifier.py
src/ccounter/plates.py
src/ccounter/plate_reader.py
src/ccounter/track_plate_manager.py
src/ccounter/anpr_worker.py
src/ccounter/stats.py
src/ccounter/export_public_json.py
src/ccounter/publish_public_site.py
src/ccounter/show_events.py
```

Important local/private files:

```text
.env
data/ccounter.db
data/snapshots/
data/plates_found.txt
logs/
```

Public website files:

```text
public/index.html
public/stats.json
```

## Git rules

Do not commit:

```text
.env
data/
logs/
exports/
```

Safe to commit:

```text
source code
.env.example
README.md
PLAN.md
docs/
public/index.html
```

Be careful with:

```text
public/stats.json
```

It should only contain safe public data.
