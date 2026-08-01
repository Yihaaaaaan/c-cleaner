@echo off
rem Full rescan: scan C: -> analyze -> report -> server + browser
cd /d "%~dp0"
python main.py
pause
