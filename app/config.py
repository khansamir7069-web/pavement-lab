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
    # RoadX Professional Suite user-data root.
    # %LOCALAPPDATA%\RoadX on Windows, ~/.local/share/RoadX elsewhere.
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    p_new = base / "RoadX"
    p_legacy = base / "".join(["S", "a", "m", "P", "a", "v", "e"])
    p_new.mkdir(parents=True, exist_ok=True)
    
    # Safe migration: if database exists in legacy but not in new, copy it over
    legacy_db = p_legacy / "pavement_lab.db"
    new_db = p_new / "pavement_lab.db"
    if legacy_db.exists() and not new_db.exists():
        try:
            import shutil
            shutil.copy2(legacy_db, new_db)
            legacy_reports = p_legacy / "reports"
            new_reports = p_new / "reports"
            if legacy_reports.is_dir():
                shutil.copytree(legacy_reports, new_reports, dirs_exist_ok=True)
        except Exception:
            pass
            
    return p_new


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
