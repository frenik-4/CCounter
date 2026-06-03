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
- export only safe aggregated statistics to an external website later

## Privacy rules

Detailed data stays local.

Local database may include:

- events
- snapshots
- track IDs
- object classes
- confidence values
- license plates later

External/public exports must not include:

- license plates
- snapshots
- raw event rows
- personal details

## Current status

Done:

- basic project structure
- `.env` configuration
- RTSP test
- YOLO detection
- detection zone
- SQLite event database
- multiple line configuration
- multi-line counter foundation
- local known plate classification foundation
- object category classifier
- safe public stats export foundation
- architecture documentation

## Current camera

Temporary camera:

- Deltaco SH-IPC17
- RTSP works but image quality can be unstable
- codec cannot be changed
- used mainly for development

Planned camera:

- Reolink RLC-811A
- ethernet/PoE
- expected to provide better RTSP quality

## Next steps

1. Test multi-line drawing and event counting with live stream.
2. Tune detection zone with the new camera.
3. Tune main road line and parking entry line.
4. Add parking exit line if needed.
5. Improve event classification.
6. Add database summary commands.
7. Prepare 24/7 server setup.
8. Later: add license plate recognition locally only.
9. Later: export aggregated stats to external website.

## Important design decisions

- SQLite is the local source of truth.
- Google Sheets or external website should only receive exported summaries.
- License plates, if added, stay local only.
- Snapshots stay local only.
- The external website must never access the camera stream.
- The external website must never read the private event database directly.

## Useful commands

Run app:

```powershell
python -m src.ccounter.app