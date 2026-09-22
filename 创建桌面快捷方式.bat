@echo off
rem ============================================================
rem  Create a Desktop shortcut to the launcher. Run once.
rem  ASCII-only on purpose: the actual work (and all Chinese
rem  text) lives in launcher.py, which is reliably UTF-8.
rem ============================================================
chcp 65001 >nul 2>&1
title C-Cleaner shortcut
cd /d "%~dp0"

set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
  call python -c "import sys" >nul 2>&1 && set "PYEXE=call python"
)
if not defined PYEXE (
  echo.
  echo   Python not found. Install Python 3.8+ from python.org first.
  echo.
  pause
  exit /b 1
)

%PYEXE% "%~dp0launcher.py" --shortcut
pause
