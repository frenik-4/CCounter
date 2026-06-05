@echo off
cd /d C:\dev\CCounter
C:\dev\CCounter\.venv\Scripts\python.exe -m src.ccounter.publish_public_site >> C:\dev\CCounter\logs\publish_public_site.log 2>&1
