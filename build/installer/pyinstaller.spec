# -*- mode: python ; coding: utf-8 -*-
# Pavement Lab — V1 installer spec (Phase 17).
#
# Build from the project root with:
#
#     pyinstaller build/installer/pyinstaller.spec --clean --noconfirm
#
# The legacy spec at ``build/pavement_lab.spec`` is preserved for the
# manual dev workflow; this spec is the V1 release entry point and adds
# the Phase 11–16 data files (sample corpus, golden snapshots if shipped,
# image-pipeline runtime directories) plus the bundled IITPAVE binary
# directory (binary itself is operator-supplied per
# build/installer/bundle_iitpave.md).
#
# Behaviour vs. source: identical. Frozen-path resolution flows through
# ``app.config._resource_root`` which now honours ``sys._MEIPASS``.

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent.parent   # build/installer -> repo root


# ---------------------------------------------------------------------------
# Bundled data
# ---------------------------------------------------------------------------
# Each entry: (source_path_on_disk, destination_path_inside_bundle).
# Destinations mirror the in-source layout so existing
# ``Path(__file__).resolve().parent`` lookups continue to work unchanged.
datas = [
    # Qt stylesheet
    (str(ROOT / "app" / "ui" / "style.qss"),
        "app/ui"),
    # Report templates directory (may be empty; ship the dir anyway so
    # _docx_common helpers that reference TEMPLATES_DIR don't fail).
    (str(ROOT / "app" / "reports" / "templates"),
        "app/reports/templates"),
    # Engineering data:
    #   - code_registry.json (CodeRef source-tag registry)
    #   - mix_specs.json     (compliance + mix-type catalogue)
    #   - binder_grades.json (Phase 3)
    #   - sample_projects/   (Phase 16 canonical corpus)
    (str(ROOT / "app" / "data"),
        "app/data"),
    # External binary directory (IITPAVE). The directory is bundled
    # even when empty so the runner's canonical path resolves under
    # the frozen bundle; the binary is placed there by the operator
    # per build/installer/bundle_iitpave.md.
    (str(ROOT / "app" / "external"),
        "app/external"),
]


# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
# Modules that PyInstaller's static analysis misses (typically because
# they are loaded via importlib or referenced by string).
hiddenimports = [
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "PySide6.QtCore",
    "matplotlib.backends.backend_qtagg",
    "scipy.interpolate",
    "sqlalchemy.dialects.sqlite",
    "docx",
    "docx2pdf",
    "PIL",                                 # Pillow — Phase 11
    "PIL.Image",
    "PIL.JpegImagePlugin",
]


# ---------------------------------------------------------------------------
# Excludes
# ---------------------------------------------------------------------------
excludes = [
    "tkinter",          # not used; trim bundle size
    "PyQt5", "PyQt6",   # PySide6 only
    "pytest",           # test framework not needed at runtime
]


a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
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
    name="SamPave",
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
    name="SamPave",
)
