@echo off
REM ============================================================
REM  SamPave Engineering Suite — one-click launcher
REM  - If the standalone .exe exists, run it directly (no Python needed).
REM  - Otherwise fall back to "python run.py" using whichever Python is
REM    available (in this order: project venv  →  py launcher  →  python).
REM  - If no Python is found, point the user at Setup.bat.
REM ============================================================
setlocal ENABLEDELAYEDEXPANSION

set "ROOT=%~dp0"
set "EXE=%ROOT%dist\SamPave\SamPave.exe"

if exist "%EXE%" (
    echo Launching SamPave Engineering Suite...
    start "" "%EXE%"
    exit /b 0
)

echo Standalone build not found — falling back to Python source launch.
echo.

REM Prefer the project-local venv if Setup.bat created one.
if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PY=%ROOT%.venv\Scripts\python.exe"
    goto :run
)

REM Try the official "py" launcher (recommended on Windows).
where py >nul 2>nul
if !errorlevel! EQU 0 (
    set "PY=py -3"
    goto :run
)

REM Fall back to plain python on PATH.
where python >nul 2>nul
if !errorlevel! EQU 0 (
    set "PY=python"
    goto :run
)

echo.
echo ERROR: No Python interpreter found.
echo Please run Setup.bat once to install Python and the dependencies,
echo then re-run Launch.bat.
echo.
pause
exit /b 1

:run
echo Using interpreter: %PY%
pushd "%ROOT%"
%PY% run.py
set "RC=%ERRORLEVEL%"
popd
if !RC! NEQ 0 (
    echo.
    echo SamPave exited with code !RC!.
    pause
)
exit /b !RC!
