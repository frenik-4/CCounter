#!/bin/bash
cd /home/lucky9/CCounter && exec .venv/bin/python -m src.ccounter.show_recent_plates "$@"
