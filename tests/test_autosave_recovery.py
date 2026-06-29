from __future__ import annotations

import os
import json
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config import USER_DATA_DIR
from app.db.repository import Database
from app.ui.main_window import MainWindow

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_autosave.db"
    database = Database(db_file)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_autosave_uses_user_data_dir(temp_db, monkeypatch):
    """Verify that autosave writes to USER_DATA_DIR dynamically and can be cleaned up."""
    # Ensure QApplication is initialized for widgets
    _app()
    
    # We mock MainWindow to avoid loading full database models or starting GUI loops
    with monkeypatch.context() as m:
        # We replace __init__ with a dummy method
        m.setattr(MainWindow, "__init__", lambda self, db, parent=None: None)
        mw = MainWindow(temp_db)
        mw.db = temp_db
        mw._current_project_id = 42
        
        # Patch export_project to return mock payload
        with patch("app.db.project_exchange.export_project") as mock_export:
            mock_export.return_value = {
                "project": {"work_name": "NH-48 Flexible Pavement Preset"}
            }
            
            # Trigger autosave checkpoint write
            mw.write_autosave_checkpoint()
            
            # Assert file is written in USER_DATA_DIR
            recovery_file = USER_DATA_DIR / "active_recovery.json"
            assert recovery_file.exists()
            
            # Verify file content
            with open(recovery_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["project_id"] == 42
            assert data["payload"]["project"]["work_name"] == "NH-48 Flexible Pavement Preset"
            
        # Clean checkpoint
        mw.clean_autosave_checkpoint()
        assert not recovery_file.exists()
