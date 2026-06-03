# CCounter

CCounter is a local Python application for monitoring and counting traffic from an RTSP camera stream.

The application is intended to run locally on a server or computer in the LAN.

## Features

Current or planned features:

- RTSP camera input
- YOLO object detection
- detection zone filtering
- object tracking
- multiple configurable counting lines
- SQLite event database
- local snapshots
- safe public statistics export
- local-only license plate handling later

## Privacy principle

Detailed data stays local.

The local database may contain:

- individual events
- snapshots
- object tracks
- detection confidence
- license plates, when enabled later

The external website must only receive aggregated statistics.

Public exports must not include:

- license plates
- snapshots
- raw event rows
- personal details

## Setup

Create virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create local environment file:

```powershell
copy .env.example .env
```

Run app:

```powershell
python -m src.ccounter.app
```

Run tests/helpers:

```powershell
python -m src.ccounter.config_test
python -m src.ccounter.counter_test
python -m src.ccounter.classifier_test
python -m src.ccounter.plates_test
python -m src.ccounter.stats_test
```

## Architecture

See:

```text
docs/ARCHITECTURE.md
```

## Important files

```text
src/ccounter/app.py          Main app
src/ccounter/config.py       Config and .env handling
src/ccounter/database.py     SQLite database
src/ccounter/tracker.py      Object tracking
src/ccounter/counter.py      Line crossing logic
src/ccounter/classifier.py   Category classification
src/ccounter/plates.py       Local known plate logic
src/ccounter/stats.py        Public statistics export
```

## Local-only files

These should not be committed to GitHub:

```text
.env
data/
exports/
logs/
```