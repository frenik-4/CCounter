@echo off
title CCounter

cd /d C:\dev\CCounter

if not exist logs (
    mkdir logs
)

echo Starting CCounter...
echo Project folder: C:\dev\CCounter
echo.

C:\dev\CCounter\.venv\Scripts\python.exe -m src.ccounter.app

echo.
echo CCounter stopped.
pause