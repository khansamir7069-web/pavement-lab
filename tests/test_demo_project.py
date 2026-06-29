from __future__ import annotations

import tempfile
import json
import pytest
from pathlib import Path

from app.db.repository import Database
from app.db.schema import (
    Project, StructuralDesign, StabilizedDesign, MechanisticValidation,
    TrafficAnalysis, MixDesign, MaterialQuantityDesign
)
from app.demo.demo_project_loader import create_demo_project
from app.engineering.design_audit import run_project_audit
from app.engineering.boq_engine import generate_boq
from app.reports.report_builder import build_combined_report, CombinedReportContext

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_demo_")
    db_file = Path(tmpdir) / "test_demo.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_create_demo_project(db):
    # 1. Creation of the demo project in the database
    pid = create_demo_project(db)
    assert pid is not None
    
    project = db.get_project(pid)
    assert project is not None
    assert project.work_name == "NH-48 Flexible Pavement Preset"
    
    # 2. Traffic analysis and calculated MSA
    ta = db.latest_traffic_analysis(pid)
    assert ta is not None
    assert ta.design_msa == pytest.approx(183.299, abs=1e-3)
    
    # 3. Subgrade CBR and resilient modulus values
    assert project.subgrade_cbr == 6.0
    assert project.subgrade_mr == pytest.approx(55.402, abs=1e-3)
    
    # 4. Option A (Conventional), Option B (Stabilized), and Option C (Mechanistic) design results exist
    sd = db.latest_structural_design(pid)
    assert sd is not None
    assert sd.total_pavement_thickness_mm > 0
    
    stab = db.latest_stabilized_design(pid)
    assert stab is not None
    
    mv = db.latest_mechanistic_validation(pid)
    assert mv is not None
    assert mv.fatigue_verdict == "PASS"
    assert mv.rutting_verdict == "PASS"
    
    # 5. Marshall parameters and mix design results are loaded
    with db.session() as s:
        from sqlalchemy import select
        mixes = list(s.scalars(select(MixDesign).where(MixDesign.project_id == pid)).all())
    assert len(mixes) == 2
    
    # 6. BOQ cost and quantity estimates run correctly
    boq = generate_boq(pid, db)
    assert boq is not None
    assert boq["available"] is True
    assert "options" in boq
    
    # 7. Expert audit is successfully executed
    audit_res = run_project_audit(pid, db)
    assert audit_res is not None
    assert audit_res.score >= 80
    
    # 8. Word DPR report builds without errors
    with tempfile.TemporaryDirectory() as report_dir:
        report_path = Path(report_dir) / "demo_report.docx"
        ctx = CombinedReportContext(
            project_title=project.work_name,
            work_name=project.work_name,
            client="Sample Highway Authority",
            submitted_by="Pavement Consultant Ltd."
        )
        build_combined_report(report_path, db, pid, ctx)
        assert report_path.exists()
        assert report_path.stat().st_size > 0
        
def test_create_fresh_copy(db):
    pid1 = create_demo_project(db)
    
    # Create fresh copy
    suffix = "2026-06-25 12:45:00"
    pid2 = create_demo_project(db, name_suffix=suffix)
    assert pid2 is not None
    assert pid2 != pid1
    
    project2 = db.get_project(pid2)
    assert project2.work_name == f"NH-48 Flexible Pavement Preset (Copy - {suffix})"
    
    # Verify that the original project still exists
    project1 = db.get_project(pid1)
    assert project1 is not None
    assert project1.work_name == "NH-48 Flexible Pavement Preset"
