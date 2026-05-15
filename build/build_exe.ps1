# Build script for Pavement Lab (Windows PowerShell).
# Run from the project root:
#     powershell -ExecutionPolicy Bypass -File build/build_exe.ps1

$ErrorActionPreference = "Stop"

Write-Host "==> Installing dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "==> Running parity tests"
python -m pytest tests/test_excel_parity.py -q
if ($LASTEXITCODE -ne 0) {
    throw "Parity tests failed — refusing to package."
}

Write-Host "==> Building executable with PyInstaller"
pyinstaller build/pavement_lab.spec --clean --noconfirm

Write-Host ""
Write-Host "==> Build complete."
Write-Host "Output: $(Resolve-Path dist/PavementLab)"
Write-Host "Launch: dist/PavementLab/PavementLab.exe"
