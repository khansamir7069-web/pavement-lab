"""Application paths and runtime configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource_root() -> Path:
    # Source mode: APP_DIR is the ``app/`` directory itself (this file
    # lives at app/config.py).
    # Frozen mode (PyInstaller): the bundle ships our ``app/`` tree at
    # ``sys._MEIPASS / "app"`` because the spec's ``datas`` entries
    # preserve the ``"app/..."`` destination prefix. Returning
    # ``sys._MEIPASS / "app"`` keeps APP_DIR semantically consistent
    # across source and frozen — every caller (data loaders, templates,
    # ui stylesheet, external/iitpave) sees the same layout.
    mei = getattr(sys, "_MEIPASS", None) or getattr(os, "_MEIPASS", None)
    if mei:
        return Path(mei) / "app"
    return Path(__file__).resolve().parent


def _user_data_root() -> Path:
    # SamPave V1 user-data root.
    # %LOCALAPPDATA%\SamPave on Windows, ~/.local/share/SamPave elsewhere.
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    p = base / "SamPave"
    p.mkdir(parents=True, exist_ok=True)
    return p


APP_DIR = _resource_root()
USER_DATA_DIR = _user_data_root()
DB_PATH = USER_DATA_DIR / "pavement_lab.db"
REPORTS_DIR = USER_DATA_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = APP_DIR / "reports" / "templates"

# Phase 11 — Image Evidence Foundation.
# Per-survey JPEGs live under IMAGES_DIR / "condition" / <project_id> / <survey_id>;
# sub-trees are created lazily by app.core.condition_survey.image_pipeline.
IMAGES_DIR = USER_DATA_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)
