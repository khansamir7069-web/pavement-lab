# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Pavement Lab.
# Run from the project root:
#     pyinstaller build/pavement_lab.spec --clean --noconfirm

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "app" / "ui" / "style.qss"), "app/ui"),
    (str(ROOT / "app" / "reports" / "templates"), "app/reports/templates"),
    (str(ROOT / "app" / "data"), "app/data"),
]

hiddenimports = [
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "PySide6.QtCore",
    "matplotlib.backends.backend_qtagg",
    "scipy.interpolate",
    "sqlalchemy.dialects.sqlite",
    "docx",
    "docx2pdf",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PavementLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PavementLab",
)
