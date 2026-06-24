from __future__ import annotations

import os
import json
import tempfile
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QFormLayout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.db.repository import Database
from app.db.schema import Project
from app.ui.main_window import MainWindow
from app.ui.widgets.project_form import ProjectForm
from app.ui.widgets.module_hub import ModuleHub

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_exe_smoke_")
    db_file = Path(tmpdir) / "test_exe_smoke.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_project_setup_contains_correct_fields(db):
    """Verify that Project Setup form contains only the 12 specified metadata fields and no Mix Type / Binder Grade."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    form = ProjectForm(db)
    
    # 1. Get all form layout labels/rows
    layout = form.findChild(QFormLayout)
    assert layout is not None
    
    fields_in_layout = []
    for i in range(layout.rowCount()):
        label_widget = layout.itemAt(i, QFormLayout.LabelRole).widget()
        if label_widget:
            fields_in_layout.append(label_widget.text())
            
    expected_fields = [
        "Project Name",
        "Client Name",
        "Location",
        "Road Category",
        "Highway Type",
        "Carriageway",
        "Design Standard",
        "Design Life",
        "Consultant Name",
        "Checked By",
        "Report ID",
        "Date"
    ]
    
    # Verify exact match of the 12 fields
    assert fields_in_layout == expected_fields
    
    # Verify that Mix Type and Binder Grade are NOT in the layout
    assert "Mix Type" not in fields_in_layout
    assert "Binder Grade" not in fields_in_layout

def test_ten_stage_workflow_and_next_step_assistant(db):
    """Verify that the module hub has the 10-stage workflow and the Next Step Assistant is visible."""
    _app()
    hub = ModuleHub()
    
    # Verify the 10 stages in the keys dictionary or cards mapping
    expected_stages = [
        "project",
        "traffic",
        "subgrade",
        "structural",
        "stabilized",
        "iitpave_status",
        "mix_design",
        "material_qty",
        "engineering_review",
        "submission"
    ]
    
    assert list(hub._cards.keys()) == expected_stages
    
    # Verify next step assistant card exists and is not hidden
    assert hub.assistant_card is not None
    assert hub.assistant_card.isHidden() is False

def test_legacy_projects_open_successfully(db):
    """Verify that old/legacy projects can be opened and load correctly."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    # Create an old legacy project directly in DB
    with db.session() as s:
        p = Project(
            work_name="Old Project V2",
            is_legacy=True,
            modules_json=None
        )
        s.add(p)
        s.flush()
        legacy_id = p.id
        
    main = MainWindow()
    
    # Open the legacy project
    main._on_open_project(legacy_id)
    assert main._current_project_id == legacy_id
    
    # Verify the project loads onto the project setup form
    assert main.project_form.work_name.text() == "Old Project V2"
    
    # Verify the status is initialized cleanly
    status = db.get_module_status(legacy_id)
    assert status["traffic"] == "needs_review"
    assert status["structural"] == "needs_review"
