from __future__ import annotations

import os
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.db.repository import Database
from app.ui.main_window import MainWindow

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ui_cleanup.db"
    database = Database(db_file)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_ui_card_navigation_and_popups(temp_db):
    _app()
    import app.db.repository as repo
    repo._singleton = temp_db
    
    # Create project to enable cards click
    pid = temp_db.create_project(
        client_id=1,
        work_name="Test Project",
        subgrade_cbr=6.0,
        subgrade_mr=50.0,
        road_category="NH / SH"
    )
    temp_db.initialize_workflow_statuses(pid.id)
    
    # Set pre-requisites status to bypass sequence gates
    temp_db.set_module_status(pid.id, "structural", "complete")
    temp_db.set_module_status(pid.id, "stabilized", "complete")
    
    # Save a mock traffic analysis and structural design to satisfy routing sequence gates
    from app.core import TrafficInput, compute_traffic_analysis
    from app.db.schema import StructuralDesign
    ta_in = TrafficInput(initial_cvpd=2000.0)
    temp_db.save_traffic_analysis(project_id=pid.id, result=compute_traffic_analysis(ta_in))
    with temp_db.session() as s:
        sd = StructuralDesign(project_id=pid.id, inputs_json="{}")
        s.add(sd)
        s.flush()
    
    main = MainWindow()
    main._on_open_project(pid.id)
    
    # Verify developer tools hidden by default
    assert main.dev_tools_widget.isHidden() is True
    
    # Trigger Ctrl+Shift+D shortcut toggle helper
    main._toggle_developer_tools()
    assert main.dev_tools_widget.isHidden() is False
    main._toggle_developer_tools()
    assert main.dev_tools_widget.isHidden() is True
    
    # Test card navigation for all modules
    stages = [
        ("project", "project"),
        ("traffic", "traffic"),
        ("subgrade", "subgrade"),
        ("structural", "structural"),
        ("stabilized", "stabilized"),
        ("iitpave_status", "iitpave_status"),
        ("mix_design", "inputs"),
        ("material_qty", "material_qty"),
        ("engineering_review", "engineering_review"),
        ("submission", "submission")
    ]
    
    for key, page_key in stages:
        main._on_module_selected(key)
        assert main.stack.currentIndex() == main._page_keys[page_key]

def test_iitpave_status_indicator(temp_db):
    _app()
    import app.db.repository as repo
    repo._singleton = temp_db
    
    main = MainWindow()
    
    # Without real executable, status indicator should show "Decision Support Mode — IITPAVE executable not connected"
    main.iitpave_status.refresh()
    status_text = main.iitpave_status.lbl_engine_status.text()
    assert "IITPAVE NOT CONNECTED" in status_text
