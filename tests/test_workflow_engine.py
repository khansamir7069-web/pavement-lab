from __future__ import annotations

import os
import json
import tempfile
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Silence QMessageBox blocking modal dialog calls in tests
QMessageBox.information = staticmethod(lambda *a, **k: 0)
QMessageBox.warning     = staticmethod(lambda *a, **k: 0)
QMessageBox.critical    = staticmethod(lambda *a, **k: 0)

from app.db.repository import Database
from app.db.schema import Project, StructuralDesign, StabilizedDesign
from app.ui.widgets.project_form import ProjectForm
from app.ui.widgets.module_hub import ModuleCard
from app.ui.main_window import MainWindow

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_workflow_")
    db_file = Path(tmpdir) / "test_workflow.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_new_project_setup_fields_and_is_legacy_default(db):
    """Verify that a new project creates the correct 12 metadata fields and is_legacy is False."""
    _app()
    # Create via db
    proj = db.create_project(
        work_name="Highway NH-2 Target",
        location="Km 45 to 90",
        road_category="NH / SH",
        highway_type="National Highway",
        carriageway="Four-lane divided carriageway",
        design_standard="IRC:37-2018",
        design_life=20,
        consultant="Aegis Consulting",
        checked_by="Senior Auditor",
        report_id="REP-2026-001",
        project_date="24-Jun-2026"
    )
    assert proj.id is not None
    assert proj.is_legacy == 0
    
    # Retrieve project
    p = db.get_project(proj.id)
    assert p.work_name == "Highway NH-2 Target"
    assert p.location == "Km 45 to 90"
    assert p.road_category == "NH / SH"
    assert p.highway_type == "National Highway"
    assert p.carriageway == "Four-lane divided carriageway"
    assert p.design_standard == "IRC:37-2018"
    assert p.design_life == 20
    assert p.consultant == "Aegis Consulting"
    assert p.checked_by == "Senior Auditor"
    assert p.report_id == "REP-2026-001"
    assert p.project_date == "24-Jun-2026"

def test_legacy_project_status_migration(db):
    """Verify that opening a legacy project initializes missing stages to 'needs_review'."""
    # 1. Manually insert project with is_legacy=1
    with db.session() as s:
        p = Project(
            work_name="Legacy Project 2024",
            is_legacy=True,
            modules_json=None  # Simulate empty/uninitialized workflow status
        )
        s.add(p)
        s.flush()
        legacy_id = p.id

    # 2. Get status -> should trigger migration
    status = db.get_module_status(legacy_id)
    
    # Missing stages should be needs_review for legacy project
    assert status["project"] == "complete"
    assert status["traffic"] == "needs_review"
    assert status["subgrade"] == "needs_review"
    assert status["structural"] == "needs_review"
    assert status["stabilized"] == "needs_review"
    assert status["mix_design"] == "needs_review"
    assert status["material_qty"] == "needs_review"
    assert status["engineering_review"] == "needs_review"
    assert status["submission"] == "needs_review"

def test_new_project_status_defaults(db):
    """Verify that a new project starts with empty/not started stages except Project Setup."""
    proj = db.create_project(work_name="New Project Workflow")
    status = db.get_module_status(proj.id)
    
    assert status["project"] == "complete"
    assert status["traffic"] == "empty"
    assert status["subgrade"] == "empty"
    assert status["structural"] == "empty"

def test_module_card_status_dropdown_completed_restriction():
    """Verify that the user cannot select 'complete' manually from the ModuleCard combo box."""
    _app()
    card = ModuleCard("mix_design", "Mix Design", "Design aggregate mix", None)
    
    # 1. If current status is 'empty'
    card.set_status("empty")
    items = [card.badge.itemData(i) for i in range(card.badge.count())]
    assert "complete" not in items
    assert card.badge.currentData() == "empty"
    
    # 2. If current status is 'complete' (system-derived)
    card.set_status("complete")
    items = [card.badge.itemData(i) for i in range(card.badge.count())]
    assert "complete" in items
    assert card.badge.currentData() == "complete"

def test_sequence_gates_hard_vs_soft(db):
    """Verify that sequence gates block new projects and warn/allow legacy projects."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    main = MainWindow()
    
    # Create new project (not legacy)
    new_proj = db.create_project(work_name="New Route Gate Test")
    main._on_open_project(new_proj.id)
    
    # Reset status of structural to empty
    db.set_module_status(new_proj.id, "structural", "empty")
    
    # Navigate to Mix Design: should block navigation (current page stays 'project' or 'hub')
    main._show_page("hub")
    main._on_module_selected("mix_design")
    assert main.stack.currentWidget() != main.inputs
    
    # Create legacy project
    with db.session() as s:
        p = Project(
            work_name="Legacy Route Gate Test",
            is_legacy=True,
            modules_json=json.dumps({"project": "complete", "structural": "needs_review"})
        )
        s.add(p)
        s.flush()
        legacy_id = p.id
        
    main._on_open_project(legacy_id)
    main._show_page("hub")
    main._on_module_selected("mix_design")
    # Soft gate should show warning and proceed, changing active page to inputs panel
    assert main.stack.currentWidget() == main.inputs

def test_iitpave_verification_gate(db):
    """Verify IITPAVE verification gate blocks if no design data exists, even for legacy."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    main = MainWindow()
    
    # Create legacy project with absolutely no design data (no layers)
    with db.session() as s:
        p = Project(
            work_name="Legacy No Layers Test",
            is_legacy=True,
            modules_json=json.dumps({"project": "complete", "structural": "needs_review", "stabilized": "needs_review"})
        )
        s.add(p)
        s.flush()
        legacy_id = p.id
        
    main._on_open_project(legacy_id)
    main._show_page("hub")
    main._on_module_selected("iitpave_status")
    # Should block completely since no layers exist at all
    assert main.stack.currentWidget() != main.iitpave_status
    
    # Add a structural design record to DB
    with db.session() as s:
        sd = StructuralDesign(
            project_id=legacy_id,
            inputs_json="{}"
        )
        s.add(sd)
        s.flush()
        
    main._on_open_project(legacy_id)
    main._show_page("hub")
    main._on_module_selected("iitpave_status")
    # Should pass soft gate warning since design data exists
    assert main.stack.currentWidget() == main.iitpave_status
