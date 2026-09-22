@echo off
rem ============================================================
rem  C-Cleaner desktop app. Double-click this file.
rem  Kept ASCII-only on purpose: Chinese text in a .bat breaks
rem  under non-UTF8 code pages. All UI text lives in Python.
rem
rem  Launches desktop.py with a windowless interpreter (pyw /
rem  pythonw) so no black console box is left behind. The console
rem  menu still exists: run "python launcher.py".
rem ============================================================
title C-Cleaner
cd /d "%~dp0"

rem -- Windowless interpreter first. "pyw" is C:\Windows\pyw.exe.
where pyw >nul 2>&1 && (
  start "" pyw -3 "%~dp0desktop.py" %*
  exit /b 0
)

rem -- Fall back to a console interpreter. "py" (C:\Windows\py.exe)
rem    before "python": python may be a pyenv .bat shim, which needs
rem    CALL or it never returns here, and may be the MS Store stub.
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
  call python -c "import sys" >nul 2>&1 && set "PYEXE=call python"
)
if not defined PYEXE (
  echo.
  echo   Python not found.
  echo   Install Python 3.10+ from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

%PYEXE% "%~dp0desktop.py" %*
if errorlevel 1 pause
