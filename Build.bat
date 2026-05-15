@echo off
REM ============================================================
REM  Pavement Lab — clean rebuild of the standalone .exe.
REM  Requires Setup.bat to have run at least once.
REM ============================================================
setlocal ENABLEDELAYEDEXPANSION

set "ROOT=%~dp0"
pushd "%ROOT%"

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo Virtual environment missing. Run Setup.bat first.
    popd
    pause
    exit /b 1
)

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

echo Running Excel-parity tests before build...
"%VENV_PY%" -m pytest tests\test_excel_parity.py -q
if !errorlevel! NEQ 0 (
    echo Parity tests failed. Refusing to package.
    popd
    pause
    exit /b 1
)

if exist "%ROOT%build\PavementLab" rmdir /S /Q "%ROOT%build\PavementLab"
if exist "%ROOT%dist\PavementLab" rmdir /S /Q "%ROOT%dist\PavementLab"

echo Building .exe with PyInstaller...
"%VENV_PY%" -m PyInstaller build\pavement_lab.spec --clean --noconfirm
if !errorlevel! NEQ 0 (
    echo Build failed.
    popd
    pause
    exit /b 1
)

echo.
echo Build complete: dist\PavementLab\PavementLab.exe
echo Run Launch.bat to start the app.
popd
pause
exit /b 0
