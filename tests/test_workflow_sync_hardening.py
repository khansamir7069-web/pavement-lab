import json
import socket
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import pytest

from app.db.repository import Database
from app.db.schema import Project, TrafficAnalysis, StructuralDesign, MaterialQuantityDesign
from app.core import TrafficInput, TrafficResult, StructuralInput, StructuralResult, MaterialQuantityResult
from app.core import PavementLayer
from app.core.material_quantity.layer_quantity import MaterialQuantityInput

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_workflow_sync_hardening_")
    db_file = Path(tmpdir) / "test_sync_hardening.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_database_migration_and_defaults(db):
    """Test that migration adds new columns and handles legacy projects safely."""
    with db.session() as s:
        p = Project(work_name="Migration Test")
        s.add(p)
        s.flush()
        
        assert p.override_history_json is None
        assert p.sync_version == 1 or p.sync_version is None
        assert p.sync_state is None
        assert p.audit_history_json is None
        
        state = db._get_sync_state_from_project(p)
        assert "versions" in state
        assert "synced_with" in state
        assert state["versions"]["traffic"] == 1

def test_override_history_append_only(db):
    """Test that override history appends new entries without losing past logs."""
    with db.session() as s:
        p = Project(work_name="Override Test")
        s.add(p)
        s.flush()
        pid = p.id

    db.append_override_history(
        project_id=pid,
        field_name="initial_cvpd",
        original_val=2000.0,
        previous_val=2000.0,
        new_val=2500.0,
        reason="Revised field survey data",
        module_name="Structural",
        user="TestUser"
    )

    db.append_override_history(
        project_id=pid,
        field_name="initial_cvpd",
        original_val=2000.0,
        previous_val=2500.0,
        new_val=2700.0,
        reason="Additional peak traffic adjustment",
        module_name="Structural",
        user="TestUser"
    )

    p_check = db.get_project(pid)
    assert p_check.override_history_json is not None
    history = json.loads(p_check.override_history_json)
    
    assert len(history) == 2
    assert history[0]["field_name"] == "initial_cvpd"
    assert history[0]["original_val"] == 2000.0
    assert history[0]["previous_val"] == 2000.0
    assert history[0]["new_val"] == 2500.0
    assert history[0]["reason"] == "Revised field survey data"
    assert history[0]["user"] == "TestUser"
    assert history[0]["machine_id"] == socket.gethostname()

    assert history[1]["field_name"] == "initial_cvpd"
    assert history[1]["original_val"] == 2000.0
    assert history[1]["previous_val"] == 2500.0
    assert history[1]["new_val"] == 2700.0
    assert history[1]["reason"] == "Additional peak traffic adjustment"

def test_sync_status_engine_state_transitions(db):
    """Test the complete state transitions of the sync engine (Synced, Out of Sync, Manual Override)."""
    with db.session() as s:
        p = Project(work_name="Sync Engine Test")
        s.add(p)
        s.flush()
        pid = p.id

    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Synced"
    assert statuses["material_qty"] == "Synced"

    t_res = TrafficResult(
        inputs=TrafficInput(initial_cvpd=2000.0, growth_rate_pct=7.5, design_life_years=15),
        vdf_used=2.5,
        ldf_used=0.75,
        growth_factor=22.4,
        design_msa=12.5,
        aashto_esal=1.8e6,
        traffic_category="High"
    )
    db.save_traffic_analysis(project_id=pid, result=t_res)

    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Out of Sync"

    s_res = StructuralResult(
        inputs=StructuralInput(initial_cvpd=2000.0, growth_rate_pct=7.5, design_life_years=15, subgrade_cbr_pct=5.0),
        design_msa=12.5,
        growth_factor=22.4,
        subgrade_mr_mpa=45.0,
        total_pavement_thickness_mm=40.0,
        composition=(PavementLayer(name="BC", material="Bituminous Concrete", thickness_mm=40.0, modulus_mpa=3000.0),)
    )
    db.save_structural_design(project_id=pid, result=s_res)

    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Synced"
    assert statuses["material_qty"] == "Out of Sync"

    mq_res = MaterialQuantityResult(
        inputs=MaterialQuantityInput(road_length_m=1000.0, carriageway_width_m=7.0, shoulder_width_m=1.5, layers=()),
        layers=(),
        total_layer_tonnage_t=1500.0,
        total_binder_tonnage_t=75.0,
        total_area_m2=7000.0
    )
    db.save_material_quantity(project_id=pid, result=mq_res)

    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Synced"
    assert statuses["material_qty"] == "Synced"

    db.save_traffic_analysis(project_id=pid, result=t_res)
    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Out of Sync"

    s_res_override = StructuralResult(
        inputs=StructuralInput(
            initial_cvpd=2500.0, growth_rate_pct=7.5, design_life_years=15, subgrade_cbr_pct=5.0,
            overrides={"active": True, "reason": "Engineering judgement"}
        ),
        design_msa=15.5,
        growth_factor=22.4,
        subgrade_mr_mpa=45.0,
        total_pavement_thickness_mm=40.0,
        composition=(PavementLayer(name="BC", material="Bituminous Concrete", thickness_mm=40.0, modulus_mpa=3000.0),)
    )
    db.save_structural_design(project_id=pid, result=s_res_override)
    statuses = db.get_all_sync_statuses(pid)
    assert statuses["structural"] == "Manual Override"

def test_project_audit_trail(db):
    """Test that project audit actions are appended to the project's audit logs."""
    with db.session() as s:
        p = Project(work_name="Audit Trail Test")
        s.add(p)
        s.flush()
        pid = p.id

    db.log_project_audit(pid, "structural", "Manual Override", "Field overridden")
    db_test = db
    db_test.log_project_audit(pid, "material_qty", "Refresh", "BOQ refreshed from source")

    p_check = db.get_project(pid)
    assert p_check.audit_history_json is not None
    audit = json.loads(p_check.audit_history_json)
    
    assert len(audit) == 2
    assert audit[0]["module"] == "structural"
    assert audit[0]["action"] == "Manual Override"
    assert audit[0]["detail"] == "Field overridden"
    
    assert audit[1]["module"] == "material_qty"
    assert audit[1]["action"] == "Refresh"
    assert audit[1]["detail"] == "BOQ refreshed from source"
