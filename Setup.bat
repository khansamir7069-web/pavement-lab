@echo off
REM ============================================================
REM  Pavement Lab — first-time setup for a fresh Windows machine.
REM
REM  What this does:
REM    1. Locates a usable Python 3.11+ interpreter.
REM       - If none, downloads and installs the official 64-bit Python.
REM    2. Creates a project-local virtual environment at .venv\
REM    3. Upgrades pip and installs requirements.txt into the venv.
REM    4. Optionally builds the standalone .exe via PyInstaller.
REM
REM  After this completes, Launch.bat works.
REM ============================================================
setlocal ENABLEDELAYEDEXPANSION

set "ROOT=%~dp0"
pushd "%ROOT%"

echo.
echo =====================================================
echo   Pavement Lab — setup
echo =====================================================
echo.

REM --- Step 1: find or install Python -------------------------------------
set "PY_CMD="

REM Prefer the py launcher
where py >nul 2>nul
if !errorlevel! EQU 0 (
    py -3 --version >nul 2>nul
    if !errorlevel! EQU 0 (
        for /f "tokens=2" %%v in ('py -3 --version 2^>^&1') do set "PYVER=%%v"
        echo Found Python via py launcher: !PYVER!
        set "PY_CMD=py -3"
    )
)

if "%PY_CMD%"=="" (
    where python >nul 2>nul
    if !errorlevel! EQU 0 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
        echo Found Python on PATH: !PYVER!
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo No Python interpreter found.
    echo Downloading and installing Python 3.12 (64-bit) for the current user...
    set "PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
    set "PY_INSTALLER=%TEMP%\python-3.12.7-amd64.exe"
    powershell -NoProfile -ExecutionPolicy Bypass ^
        -Command "Invoke-WebRequest -UseBasicParsing -Uri '!PY_URL!' -OutFile '!PY_INSTALLER!'"
    if not exist "!PY_INSTALLER!" (
        echo ERROR: Failed to download Python installer.
        echo Please install Python 3.11+ manually from https://www.python.org/downloads/
        popd
        pause
        exit /b 1
    )
    echo Running installer (silent, per-user, adds to PATH)...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
    if !errorlevel! NEQ 0 (
        echo ERROR: Python installer returned errorlevel !errorlevel!.
        popd
        pause
        exit /b 1
    )
    REM Refresh PATH for current cmd.exe session
    for /f "delims=" %%P in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('PATH','User')"') do set "PATH=%%P;%PATH%"
    set "PY_CMD=py -3"
)

echo Using: %PY_CMD%

REM --- Step 2: create .venv ----------------------------------------------
if exist "%ROOT%.venv\Scripts\python.exe" (
    echo Reusing existing virtual environment at .venv\
) else (
    echo Creating virtual environment at .venv\ ...
    %PY_CMD% -m venv "%ROOT%.venv"
    if !errorlevel! NEQ 0 (
        echo ERROR: Could not create virtual environment.
        popd
        pause
        exit /b 1
    )
)

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

REM --- Step 3: install dependencies --------------------------------------
echo Upgrading pip in venv...
"%VENV_PY%" -m pip install --upgrade pip wheel setuptools

echo Installing project requirements...
"%VENV_PY%" -m pip install -r requirements.txt
if !errorlevel! NEQ 0 (
    echo ERROR: pip install failed.
    popd
    pause
    exit /b 1
)

REM --- Step 4: optional .exe build ---------------------------------------
echo.
choice /M "Build standalone Windows .exe with PyInstaller now? (recommended)"
if !errorlevel! EQU 1 (
    echo Building .exe...
    "%VENV_PY%" -m PyInstaller build\pavement_lab.spec --clean --noconfirm
    if !errorlevel! NEQ 0 (
        echo WARNING: PyInstaller build failed — you can still run via Launch.bat
        echo          which will fall back to the Python source.
    ) else (
        echo .exe built at dist\PavementLab\PavementLab.exe
    )
)

echo.
echo =====================================================
echo   Setup complete.
echo   Double-click Launch.bat to start Pavement Lab.
echo =====================================================
popd
pause
exit /b 0
