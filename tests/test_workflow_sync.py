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
from app.db.schema import Project, StructuralDesign, TrafficAnalysis, MaterialQuantityDesign
from app.ui.main_window import MainWindow
from app.core import TrafficInput, compute_traffic_analysis

def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_workflow_sync_")
    db_file = Path(tmpdir) / "test_sync.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_structural_design_reads_traffic_and_subgrade(db):
    """Verify that Structural Design panel loads Traffic and Subgrade CBR/Mr from DB."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    # 1. Create a project and save Subgrade data
    proj = db.create_project(work_name="NH-99 Sync Test")
    db.update_project(proj.id, subgrade_cbr=6.5, subgrade_mr=61.2)
    
    # 2. Save Traffic Analysis data
    ta_in = TrafficInput(
        initial_cvpd=4500.0,
        growth_rate_pct=8.0,
        design_life_years=20,
        vdf=4.2,
        ldf=0.75,
        directional_distribution=0.55,
        lane_distribution=0.85
    )
    ta_res = compute_traffic_analysis(ta_in)
    db.save_traffic_analysis(project_id=proj.id, result=ta_res)
    db.set_module_status(proj.id, "traffic", "complete")
    db.set_module_status(proj.id, "subgrade", "complete")
    
    # 3. Open project in Main Window and load Structural Design panel
    main = MainWindow()
    main._on_open_project(proj.id)
    main.structural.set_project(proj.id, proj.work_name)
    
    # Inputs should be populated from traffic & subgrade
    assert main.structural.cvpd.value() == 4500.0
    assert main.structural.growth.value() == 8.0
    assert main.structural.design_life.value() == 20
    assert main.structural.vdf.value() == 4.2
    assert main.structural.ldf.value() == 0.75
    assert main.structural.cbr.value() == 6.5
    assert main.structural.mr_mpa.value() == 61.2
    
    # By default, inputs are NOT editable (read-only)
    assert not main.structural.cvpd.isEnabled()
    assert not main.structural.cbr.isEnabled()
    assert not main.structural.chk_override.isChecked()

def test_manual_override_flow_and_persistence(db):
    """Verify Manual Override checkbox enables fields, saves reason/original values, and displays badge."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    # 1. Setup project with traffic and subgrade
    proj = db.create_project(work_name="NH-99 Override Test")
    db.update_project(proj.id, subgrade_cbr=5.0, subgrade_mr=50.0)
    
    ta_in = TrafficInput(initial_cvpd=2000.0, growth_rate_pct=7.5, design_life_years=15, vdf=2.5, ldf=0.75)
    ta_res = compute_traffic_analysis(ta_in)
    db.save_traffic_analysis(project_id=proj.id, result=ta_res)
    
    main = MainWindow()
    main._on_open_project(proj.id)
    panel = main.structural
    panel.set_project(proj.id, proj.work_name)
    
    # Checkbox override
    panel.chk_override.setChecked(True)
    assert panel.cvpd.isEnabled()
    assert not panel.txt_override_reason.isHidden()
    assert not panel.lbl_override_badge.isHidden()
    
    # Edit values
    panel.cvpd.setValue(3500.0)
    panel.txt_override_reason.setText("Modified CVPD per latest count")
    
    # Save
    panel._on_compute()
    panel._on_save()
    
    # Verify in DB
    sd = db.latest_structural_design(proj.id)
    assert sd is not None
    inputs_dict = json.loads(sd.inputs_json)
    
    overrides = inputs_dict.get("overrides", {})
    assert overrides.get("active") is True
    assert overrides.get("reason") == "Modified CVPD per latest count"
    assert "initial_cvpd" in overrides.get("values", {})
    assert overrides["values"]["initial_cvpd"]["original"] == 2000.0
    assert overrides["values"]["initial_cvpd"]["manual"] == 3500.0
    
    # Load back in UI
    panel.set_project(proj.id, proj.work_name)
    assert panel.chk_override.isChecked()
    assert panel.cvpd.value() == 3500.0
    assert panel.txt_override_reason.text() == "Modified CVPD per latest count"

def test_boq_automatically_imports_thickness(db):
    """Verify that the BOQ panel automatically loads layer thicknesses from structural design."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    proj = db.create_project(work_name="BOQ Sync Test")
    
    # Save a structural design
    comp = [
        {"name": "Bituminous Concrete (BC)", "thickness_mm": 40.0, "material": "BC"},
        {"name": "Dense Bituminous Macadam (DBM)", "thickness_mm": 85.0, "material": "DBM"}
    ]
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json="{}",
            design_msa=10.0,
            growth_factor=1.5,
            subgrade_mr_mpa=50.0,
            total_pavement_thickness_mm=125.0,
            composition_json=json.dumps(comp)
        )
        s.add(sd)
        s.flush()
        
    main = MainWindow()
    main._on_open_project(proj.id)
    main.material_qty.set_project(proj.id, proj.work_name)
    
    tbl = main.material_qty.tbl
    assert tbl.rowCount() >= 2
    
    # Check that BC is 40.0 and DBM is 85.0
    bc_found = False
    dbm_found = False
    for r in range(tbl.rowCount()):
        layer_type = tbl.cellWidget(r, 0).currentText()
        thick = tbl.cellWidget(r, 3).value()
        if layer_type == "BC":
            assert thick == 40.0
            bc_found = True
        elif layer_type == "DBM":
            assert thick == 85.0
            dbm_found = True
            
    assert bc_found
    assert dbm_found

def test_sequence_gates_restrictions(db):
    """Verify sequence gates block entering Structural Design and BOQ if prerequisites are missing."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    proj = db.create_project(work_name="Gate Test Project")
    
    main = MainWindow()
    main._on_open_project(proj.id)
    main._show_page("hub")
    
    # Try entering Structural Design -> should block because Traffic and Subgrade don't exist
    main._on_module_selected("structural")
    assert main.stack.currentWidget() != main.structural
    
    # Setup traffic and subgrade
    db.update_project(proj.id, subgrade_cbr=5.0, subgrade_mr=50.0)
    ta_in = TrafficInput(initial_cvpd=2000.0)
    db.save_traffic_analysis(project_id=proj.id, result=compute_traffic_analysis(ta_in))
    
    # Try entering Structural Design now -> should succeed
    main._on_module_selected("structural")
    assert main.stack.currentWidget() == main.structural
    
    # Try entering BOQ -> should block because Structural Design is not saved yet
    main._show_page("hub")
    main._on_module_selected("material_qty")
    assert main.stack.currentWidget() != main.material_qty
    
    # Save a structural design
    with db.session() as s:
        sd = StructuralDesign(project_id=proj.id, inputs_json="{}")
        s.add(sd)
        s.flush()
        
    # Try entering BOQ now -> should succeed
    main._on_module_selected("material_qty")
    assert main.stack.currentWidget() == main.material_qty

def test_submission_checklist_renders_summaries(db):
    """Verify that Submission center readiness checklist renders summary of database module values."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    proj = db.create_project(work_name="Submission Sync Test")
    db.update_project(proj.id, subgrade_cbr=5.5, subgrade_mr=55.0)
    
    # Save traffic
    ta_in = TrafficInput(initial_cvpd=3500.0)
    db.save_traffic_analysis(project_id=proj.id, result=compute_traffic_analysis(ta_in))
    
    main = MainWindow()
    main._on_open_project(proj.id)
    panel = main.submission
    panel.set_project(proj.id, proj.work_name)
    
    # HTML should show CBR and CVPD
    html = panel.lbl_readiness.text()
    assert "CBR: 5.5%" in html
    assert "Mr: 55.0 MPa" in html
    assert "CVPD: 3500" in html
    assert "Submission Sync Test" in html

def test_old_project_migration_and_compatibility(db):
    """Verify legacy projects can open, load safe default workflow statuses, and bypass sequence gates with warning."""
    _app()
    import app.db.repository as repo
    repo._singleton = db
    
    # Create legacy project manually
    with db.session() as s:
        p = Project(
            work_name="Old Legacy Project",
            is_legacy=True,
            modules_json=None
        )
        s.add(p)
        s.flush()
        legacy_id = p.id
        
    main = MainWindow()
    main._on_open_project(legacy_id)
    
    # Workflow status should migrate to needs_review
    status = db.get_module_status(legacy_id)
    assert status["traffic"] == "needs_review"
    assert status["structural"] == "needs_review"
    
    # Try navigating to Structural Design -> should allow with Warning (legacy soft gate)
    main._show_page("hub")
    main._on_module_selected("structural")
    assert main.stack.currentWidget() == main.structural
