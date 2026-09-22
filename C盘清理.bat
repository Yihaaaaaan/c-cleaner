@echo off
rem ============================================================
rem  C-Cleaner launcher. Double-click this file.
rem  Kept ASCII-only on purpose: Chinese text in a .bat breaks
rem  under non-UTF8 code pages. All UI text lives in launcher.py.
rem ============================================================
chcp 65001 >nul 2>&1
title C-Cleaner
cd /d "%~dp0"

rem -- Find Python. "py" (C:\Windows\py.exe) first: it is a real exe.
rem    "python" may be a pyenv .bat shim, which needs CALL or it never
rem    returns here, and may also be the Microsoft Store stub.
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
  call python -c "import sys" >nul 2>&1 && set "PYEXE=call python"
)
if not defined PYEXE (
  echo.
  echo   Python not found.
  echo   Install Python 3.8+ from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

%PYEXE% "%~dp0launcher.py" %*

rem Reached only when the server stops or the user quits.
if errorlevel 1 pause
