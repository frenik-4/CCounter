# CCounter Architecture

CCounter is a local traffic monitoring application.

## Main principle

CCounter runs locally on a server in the LAN.

The camera stream is processed locally. Sensitive data is stored locally only.

The external website must only receive aggregated statistics.

## Data levels

### Private local data

Stored locally in SQLite.

May include:

- detailed events
- snapshots
- track IDs
- object classes
- directions
- line names
- detection confidence
- license plates, when enabled later

This data must not be published directly.

### Public data

Generated from local events.

May include:

- hourly counts
- daily counts
- event categories
- object categories
- traffic direction summaries

Must not include:

- license plates
- snapshots
- raw event rows
- personal details

## Processing flow

```text
Camera RTSP stream
→ YOLO object detection
→ detection zone filtering
→ object tracking
→ line crossing detection
→ event classification
→ local SQLite database
→ public statistics export
→ external website
```

## Event types

Planned event types:

- road_passage
- parking_entry
- parking_exit
- detection
- unknown

## Object categories

Planned categories:

- road_traffic
- parking_traffic
- pedestrian
- bicycle
- cyclist
- motorcycle
- animal
- horse
- horse_rider
- other
- unknown

## License plates

License plate recognition may be added later.

Rules:

- license plates are stored locally only
- license plates are never exported to the public website
- known plates can be used for grouping or exclusion
- public exports must only contain aggregated statistics

## External website

The external website should not connect to the camera.

The external website should not access the private SQLite database directly.

Preferred approach:

```text
Local CCounter server
→ creates safe aggregated stats
→ pushes or uploads stats to website
```

## Current modules

```text
app.py          Main runtime application
config.py       Environment/config handling
database.py     SQLite database
tracker.py      Simple centroid tracking
counter.py      Line crossing logic
classifier.py   Object category classification
plates.py       Local known plate classification
stats.py        Safe public statistics export
```