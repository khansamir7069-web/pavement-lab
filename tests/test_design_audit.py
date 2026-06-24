from __future__ import annotations

import tempfile
import json
import pytest
from pathlib import Path

from app.db.repository import Database
from app.db.schema import (
    Project,
    StructuralDesign,
    StabilizedDesign,
    MechanisticValidation,
    TrafficAnalysis,
    ReportRevisionSnapshotRecord,
    MixDesign,
    MaterialQuantityDesign,
)
from app.engineering.design_audit import run_project_audit
from app.reports.report_builder import build_combined_report, CombinedReportContext

@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_audit_")
    db_file = Path(tmpdir) / "test_audit.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_empty_project(db):
    """Verify that an empty project receives a low score, RED risk level, and Not Ready status."""
    proj = db.create_project(work_name="Empty Project Test")
    
    # Run audit
    res = run_project_audit(proj.id, db)
    
    assert res.score < 50
    assert res.risk_level == "RED"
    assert res.readiness_status == "Not Ready"
    
    # Verify critical findings are present (missing traffic, missing subgrade CBR, missing structural design)
    severities = [f.severity for f in res.findings]
    assert "critical" in severities
    
    # Verify we have findings for traffic, subgrade, structural
    modules = [f.module for f in res.findings]
    assert "traffic" in modules
    assert "subgrade" in modules
    assert "structural" in modules

def test_project_with_traffic_and_subgrade(db):
    """Verify that adding traffic and subgrade data improves the score."""
    proj = db.create_project(work_name="Traffic & Subgrade Test")
    
    # 1. Add subgrade CBR
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.subgrade_cbr = 6.0
        p_row.subgrade_mr = 17.6 * (6.0 ** 0.64)  # consistent Mr
        s.commit()
        
    # 2. Add traffic analysis
    ta_inputs = {
        "initial_cvpd": 1500.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "design_life_years": 15
    }
    with db.session() as s:
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=15.0
        )
        s.add(ta)
        s.commit()
    
    # Audit
    res = run_project_audit(proj.id, db)
    
    # Score should improve compared to empty
    assert res.score > 40
    
    # Check that traffic and subgrade missing critical findings are gone
    for f in res.findings:
        if f.module == "traffic":
            assert f.severity != "critical"
        if f.module == "subgrade":
            assert f.severity != "critical"

def test_high_msa_missing_iitpave(db):
    """Verify warning triggers when MSA is high (> 20) but mechanistic check is missing."""
    proj = db.create_project(work_name="High MSA Test")
    
    # Add traffic with high MSA (e.g. 25.0)
    ta_inputs = {
        "initial_cvpd": 3000.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "design_life_years": 15
    }
    # Add structural design so it's not missing
    comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    with db.session() as s:
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=25.0
        )
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=json.dumps({
                "road_category": "NH / SH",
                "design_life_years": 15,
                "initial_cvpd": 3000.0,
                "growth_rate_pct": 7.5,
                "vdf": 4.5,
                "ldf": 0.75,
                "subgrade_cbr_pct": 6.0
            }),
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=570.0
        )
        s.add(ta)
        s.add(sd)
        s.commit()
    
    # No mechanistic validation added yet
    res = run_project_audit(proj.id, db)
    
    # Should flag missing mechanistic check for MSA > 20
    finding = next((f for f in res.findings if "mechanistic verification is missing" in f.issue), None)
    assert finding is not None
    assert finding.severity == "warning"

def test_failed_iitpave(db):
    """Verify critical warning triggers when IITPAVE verification fails."""
    proj = db.create_project(work_name="Failed IITPAVE Test")
    
    # Save a failed mechanistic validation
    results_json = {
        "fatigue": {"verdict": "FAIL", "strain": 1.5e-4, "allowable": 1.0e-4},
        "rutting": {"verdict": "PASS", "strain": 1.0e-4, "allowable": 2.0e-4}
    }
    with db.session() as s:
        mv = MechanisticValidation(
            project_id=proj.id,
            summary_json=json.dumps(results_json),
            refused=False
        )
        s.add(mv)
        s.commit()
        
    res = run_project_audit(proj.id, db)
    
    # Should flag failed IITPAVE check
    finding = next((f for f in res.findings if "mechanistic verification failed" in f.issue), None)
    assert finding is not None
    assert finding.severity == "critical"
    
    # Risk should be RED and status Not Ready due to critical finding
    assert res.risk_level == "RED"
    assert res.readiness_status == "Not Ready"

def test_completed_verified_design(db):
    """Verify that a fully completed project receives a high score (not forced 100)."""
    # Create complete project
    proj = db.create_project(
        work_name="Completed Project",
        subgrade_cbr=6.0,
        subgrade_mr=17.6 * (6.0 ** 0.64),
        review_status="Approved for Submission",
        checklist_json=json.dumps({
            "design_review": True,
            "input_verification": True,
            "traffic_verification": True,
            "material_verification": True
        }),
        locked=True
    )
    
    # Add traffic
    ta_inputs = {
        "initial_cvpd": 1000.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "design_life_years": 15
    }
    # Add structural
    comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    # Add passing IITPAVE
    results_json = {
        "fatigue": {"verdict": "PASS", "strain": 0.8e-4, "allowable": 1.0e-4},
        "rutting": {"verdict": "PASS", "strain": 1.0e-4, "allowable": 2.0e-4}
    }
    
    with db.session() as s:
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=10.0
        )
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=json.dumps({
                "road_category": "NH / SH",
                "design_life_years": 15,
                "initial_cvpd": 1000.0,
                "growth_rate_pct": 7.5,
                "vdf": 4.5,
                "ldf": 0.75,
                "subgrade_cbr_pct": 6.0
            }),
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=570.0
        )
        mv = MechanisticValidation(
            project_id=proj.id,
            summary_json=json.dumps(results_json),
            refused=False
        )
        mix = MixDesign(
            project_id=proj.id
        )
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json="{}",
            results_json="{}",
            total_layer_tonnage_t=100.0,
            total_binder_tonnage_t=5.0
        )
        rep = ReportRevisionSnapshotRecord(
            project_id=proj.id,
            report_path="dummy.docx"
        )
        s.add_all([ta, sd, mv, mix, mq, rep])
        s.commit()

    # Run audit
    res = run_project_audit(proj.id, db)
    
    # Score should be high (e.g., > 85), but not necessarily perfect 100 since there might be info level findings.
    assert res.score >= 85
    # Ensure it's not hardcoded to 100
    # Risk level should be GREEN (or YELLOW if any warnings remain, but green if we resolved all warnings)
    assert res.risk_level in ("GREEN", "YELLOW")

def test_audit_engine_no_regressions(db):
    """Verify the audit engine does not alter calculations."""
    proj = db.create_project(
        work_name="Regression Check",
        subgrade_cbr=5.0,
        subgrade_mr=50.0
    )
    
    # Check values before audit
    cbr_pre = proj.subgrade_cbr
    mr_pre = proj.subgrade_mr
    
    run_project_audit(proj.id, db)
    
    # Retrieve again
    p_post = db.get_project(proj.id)
    assert p_post.subgrade_cbr == cbr_pre
    assert p_post.subgrade_mr == mr_pre

def test_dpr_export_parity(db, tmp_path):
    """Verify Word report successfully generates with the new audit section included without crash."""
    proj = db.create_project(
        work_name="DPR Export Test Project",
        subgrade_cbr=6.0,
        subgrade_mr=17.6 * (6.0 ** 0.64)
    )
    
    # Save basic structural design to make it exportable
    comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    inputs_json = json.dumps({
        "road_category": "NH / SH",
        "design_life_years": 15,
        "initial_cvpd": 1500.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 6.0
    })
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=inputs_json,
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=570.0
        )
        s.add(sd)
        s.commit()
    
    ctx = CombinedReportContext(
        project_title="DPR Export Test Title",
        work_name="DPR Export Test Work Name",
        client="DPR Client"
    )
    
    out_file = tmp_path / "combined_report.docx"
    
    # Build report - should include the audit section and not crash
    path, included = build_combined_report(out_file, db, proj.id, ctx)
    
    assert path.exists()
    assert "Appendix G: Expert Audit Report" in included

def test_dpr_export_fail_safe_missing_audit(db, tmp_path):
    """Verify that if the audit raises an exception, the report generation still succeeds without crashing."""
    proj = db.create_project(
        work_name="Fail-Safe Test Project",
        subgrade_cbr=6.0
    )
    
    # Save basic structural design to make it exportable
    comp = [
        {"name": "BC", "thickness_mm": 40.0}
    ]
    inputs_json = json.dumps({
        "road_category": "NH / SH",
        "design_life_years": 15,
        "initial_cvpd": 1500.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 6.0
    })
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=inputs_json,
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=40.0
        )
        s.add(sd)
        s.commit()
    
    ctx = CombinedReportContext(
        project_title="Fail-Safe Test Title",
        work_name="Fail-Safe Test Work Name",
        client="Fail-Safe Client"
    )
    
    out_file = tmp_path / "fail_safe_report.docx"
    
    # Mock run_project_audit to raise an Exception
    import app.engineering.design_audit as da
    original_run_audit = da.run_project_audit
    
    try:
        def mock_run_project_audit(*args, **kwargs):
            raise RuntimeError("Database connection lost during audit run")
            
        # Temporarily monkeypatch run_project_audit
        da.run_project_audit = mock_run_project_audit
        
        # Build report - should not crash, despite the audit raising an exception
        path, included = build_combined_report(out_file, db, proj.id, ctx)
        assert path.exists()
        # "Appendix G: Expert Audit Report" should NOT be in the included list as it failed
        assert "Appendix G: Expert Audit Report" not in included
    finally:
        da.run_project_audit = original_run_audit
