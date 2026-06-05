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
- parking entry line
- live multi-line event counting tested
- event snapshots saved locally
- local known plate classification foundation
- object category classifier
- safe public stats export foundation
- static public dashboard
- SFTP publishing to external web hosting
- automatic public publishing foundation
- architecture documentation
- Reolink RLC-811A camera installed and tested
- basic ANPR test with EasyOCR
- ANPR can read from snapshot/crop images
- `TrackPlateManager` foundation added
- best plate candidate can be tracked per object ID
- temporary plate results are written to `data/plates_found.txt`

## Current camera

Current camera:

- Reolink RLC-811A
- Ethernet/PoE
- RTSP stream working
- better image quality than the temporary Deltaco camera
- used for current tuning and ANPR testing

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
- totals for selected day
- categories
- hourly summary
- expandable hourly events
- daily hour graph

Public dashboard must not show:

- license plates
- snapshots
- raw database rows
- private notes
- known-plate labels

## Next steps

1. Continue live testing with the Reolink camera.
2. Tune detection zone for the new camera view.
3. Tune main road line.
4. Tune parking entry line.
5. Decide whether parking events should remain hidden from the public dashboard.
6. Add parking exit line if needed.
7. Improve event classification.
8. Improve ANPR accuracy.
9. Store ANPR results in the local database instead of only `plates_found.txt`.
10. Add database summary commands.
11. Prepare Linux 24/7 server setup.
12. Move project from Windows development machine to Linux server.
13. Configure CCounter to run automatically on server boot.
14. Configure public export/publishing on the server.
15. Add monitoring/logging for 24/7 operation.

## Current ANPR status

Current ANPR implementation:

- EasyOCR is installed.
- `PlateReader` can read from image files and image arrays.
- `TrackPlateManager` keeps best plate candidate per track ID.
- ANPR can run on vehicle crops while a vehicle is visible.
- Best temporary result can be written to `data/plates_found.txt`.
- ANPR results are not yet stored in the main `events` database table.

Current limitations:

- ANPR accuracy still needs real-world testing.
- OCR may be slow if run too often.
- OCR should not run on every frame.
- OCR should focus on vehicle crops, not full-frame snapshots.
- Camera angle, zoom, shutter speed and lighting will affect results heavily.

## Planned ANPR improvement

Improved ANPR flow:

- Track each vehicle while it is visible.
- Keep best candidate image per track ID.
- Run ANPR periodically, not every frame.
- Run ANPR on vehicle crop instead of full snapshot.
- Store best plate result per track:
  - plate text
  - OCR confidence
  - snapshot/crop path
  - timestamp
- When the vehicle crosses a count line:
  - save the event
  - attach the best plate result found during the whole track
  - store this in the local database
- Match detected plates against local known plates.
- Use known plates for:
  - exclusion
  - separate grouping
  - internal reporting
- License plates must remain local only and must never be included in public exports.

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
- Google Sheets or external website should only receive exported summaries.
- License plates stay local only.
- Snapshots stay local only.
- The external website must never access the camera stream.
- The external website must never read the private event database directly.
- Public exports must be generated from filtered/safe data only.
- Parking traffic can be stored locally even if hidden from the public dashboard.

## Useful commands

Run app:

```powershell
python -m src.ccounter.app
```

Start app with batch file:

```powershell
.\start_ccounter.bat
```

Show recent events:

```powershell
python -m src.ccounter.show_events
```

Open temporary ANPR results:

```powershell
notepad data\plates_found.txt
```

Export public JSON:

```powershell
python -m src.ccounter.export_public_json
```

Publish public site:

```powershell
python -m src.ccounter.publish_public_site
```

Run helper tests:

```powershell
python -m src.ccounter.config_test
python -m src.ccounter.counter_test
python -m src.ccounter.classifier_test
python -m src.ccounter.plates_test
python -m src.ccounter.stats_test
```

Syntax check:

```powershell
python -m py_compile src\ccounter\app.py
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