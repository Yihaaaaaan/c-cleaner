@echo off
rem Open the c-cleaner report (starts local server + browser)
cd /d "%~dp0"
python serve.py
pause
