@echo off
cd /d "%~dp0"
title Wedge Studio -- District Zero

REM ── find Python ──────────────────────────────────────────────────────────
set PYTHON=

REM 1. venv (standard git ComfyUI install)
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    goto :run
)

REM 2. portable ComfyUI embedded python
if exist "python_embeded\python.exe" (
    set PYTHON=python_embeded\python.exe
    goto :run
)

REM 3. system python
where python >nul 2>&1 && set PYTHON=python && goto :run
where python3 >nul 2>&1 && set PYTHON=python3 && goto :run

echo [!] Python not found. Make sure Python is installed or run from your ComfyUI folder.
pause
exit /b 1

:run
echo.
echo   Starting Wedge Studio...
echo   Browser will open automatically.
echo   Press Ctrl+C to stop.
echo.
%PYTHON% _wedge_studio.py %*
pause
