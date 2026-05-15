"""Application paths and runtime configuration."""
from __future__ import annotations

import os
from pathlib import Path


def _resource_root() -> Path:
    # When frozen by PyInstaller, _MEIPASS points to the bundle.
    if hasattr(os, "_MEIPASS"):
        return Path(os._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def _user_data_root() -> Path:
    # %LOCALAPPDATA%\PavementLab on Windows, ~/.local/share/PavementLab elsewhere.
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    p = base / "PavementLab"
    p.mkdir(parents=True, exist_ok=True)
    return p


APP_DIR = _resource_root()
USER_DATA_DIR = _user_data_root()
DB_PATH = USER_DATA_DIR / "pavement_lab.db"
REPORTS_DIR = USER_DATA_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = APP_DIR / "reports" / "templates"
