from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
import pytest
from docx import Document

from app.db.repository import Database
from app.db.schema import Project
from app.core.structural_design import StructuralInput, StructuralResult, PavementLayer
from app.core.project_archive import generate_project_archive
from app.reports.report_builder import build_combined_report, CombinedReportContext

@pytest.fixture
def temp_db_path():
    # Use mkdtemp without instant cleanup in a with-statement to avoid Windows file locks
    tmpdir = tempfile.mkdtemp(prefix="test_consultancy_")
    db_file = Path(tmpdir) / "test_consultancy.db"
    yield db_file

@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    # Dispose the SQLAlchemy engine to release file locks on sqlite
    try:
        database.engine.dispose()
    except Exception:
        pass

def test_checklist_persistence(db):
    """Verify save_project_checklist updates review_status and checklist JSON."""
    proj = db.create_project(work_name="Test Project Checklist")
    proj_id = proj.id
    checklist_data = {
        "design_review": True,
        "input_verification": False,
        "traffic_verification": True,
        "material_verification": False,
        "iitpave_verification": "Verified",
        "reviewer_notes": "All looks good but material needs double check."
    }
    
    db.save_project_checklist(proj_id, "Under Review", checklist_data)
    
    project = db.get_project(proj_id)
    assert project.review_status == "Under Review"
    saved_checklist = json.loads(project.checklist_json)
    assert saved_checklist["design_review"] is True
    assert saved_checklist["input_verification"] is False
    assert saved_checklist["traffic_verification"] is True
    assert saved_checklist["reviewer_notes"] == "All looks good but material needs double check."

def test_accidental_edit_blocking(db):
    """Verify repository methods throw ValueError when locked=True, and unlock works."""
    proj = db.create_project(work_name="Test Project Lock")
    proj_id = proj.id
    
    # Save a structural design first (while unlocked)
    inp = StructuralInput(
        road_category="NH / SH",
        design_life_years=15,
        initial_cvpd=2000.0,
        growth_rate_pct=7.5,
        vdf=2.5,
        ldf=0.75,
        subgrade_cbr_pct=5.0,
    )
    layers = (
        PavementLayer(name="BC", thickness_mm=40.0, material="BC", modulus_mpa=3000.0, poisson=0.35),
        PavementLayer(name="DBM", thickness_mm=80.0, material="DBM", modulus_mpa=2500.0, poisson=0.35),
    )
    result = StructuralResult(
        inputs=inp,
        design_msa=15.0,
        growth_factor=1.5,
        subgrade_mr_mpa=50.0,
        composition=layers,
        total_pavement_thickness_mm=120.0,
    )
    db.save_structural_design(project_id=proj_id, result=result)
    
    # Lock project
    db.lock_project(proj_id)
    project = db.get_project(proj_id)
    assert project.locked is True
    assert project.locked_at is not None
    assert project.lock_snapshot_json is not None
    
    # Verify modification is blocked
    with pytest.raises(ValueError, match="Cannot modify a locked project"):
        db.save_structural_design(project_id=proj_id, result=result)
        
    # Unlock project
    db.unlock_project(proj_id)
    project = db.get_project(proj_id)
    assert project.locked is False
    assert project.locked_at is None
    assert project.lock_snapshot_json is None
    
    # Verify we can modify now
    db.save_structural_design(project_id=proj_id, result=result)

def test_duplication_and_revisions(db):
    """Validate project cloning, parent lineage association, and revision increments."""
    proj = db.create_project(work_name="Original Project")
    proj_id = proj.id
    inp = StructuralInput(design_life_years=15, initial_cvpd=1000.0, subgrade_cbr_pct=5.0)
    layers = (PavementLayer(name="BC", thickness_mm=40.0),)
    result = StructuralResult(inputs=inp, design_msa=10.0, growth_factor=1.2, subgrade_mr_mpa=50.0, composition=layers, total_pavement_thickness_mm=40.0)
    db.save_structural_design(project_id=proj_id, result=result)
    
    # 1. Duplicate project (Clone)
    dup_id = db.duplicate_project(proj_id)
    dup_project = db.get_project(dup_id)
    assert dup_project.work_name == "Copy of Original Project"
    assert dup_project.locked is False
    assert dup_project.parent_project_id is None
    assert dup_project.revision_number == 0
    assert db.latest_structural_design(dup_id) is not None
    
    # 2. Revisions
    db.lock_project(proj_id)
    rev_id = db.create_project_revision(proj_id, "Revision A: updated design life")
    rev_project = db.get_project(rev_id)
    assert rev_project.work_name == "Original Project"
    assert rev_project.locked is False
    assert rev_project.parent_project_id == proj_id
    assert rev_project.revision_number == 1
    
    revisions = json.loads(rev_project.revisions_json)
    assert len(revisions) == 1
    assert revisions[0]["revision_number"] == 1
    assert revisions[0]["engineer_note"] == "Revision A: updated design life"

def test_revision_diffing(db):
    """Save different thicknesses/moduli in parent and child, lock them, and verify changed parameters are logged in revisions_json."""
    parent = db.create_project(work_name="Diff Project")
    parent_id = parent.id
    
    # Parent: Thickness=40, design life=15
    inp_p = StructuralInput(design_life_years=15, subgrade_cbr_pct=5.0)
    layers_p = (PavementLayer(name="BC", thickness_mm=40.0, modulus_mpa=3000.0),)
    res_p = StructuralResult(inputs=inp_p, design_msa=10.0, growth_factor=1.2, subgrade_mr_mpa=50.0, composition=layers_p, total_pavement_thickness_mm=40.0)
    db.save_structural_design(project_id=parent_id, result=res_p)
    
    db.lock_project(parent_id)
    
    # Create revision
    child_id = db.create_project_revision(parent_id, "Revision 1 notes")
    
    # Child: Thickness=50, design life=20
    inp_c = StructuralInput(design_life_years=20, subgrade_cbr_pct=5.0)
    layers_c = (PavementLayer(name="BC", thickness_mm=50.0, modulus_mpa=3200.0),)
    res_c = StructuralResult(inputs=inp_c, design_msa=12.0, growth_factor=1.4, subgrade_mr_mpa=50.0, composition=layers_c, total_pavement_thickness_mm=50.0)
    db.save_structural_design(project_id=child_id, result=res_c)
    
    # Locking child should trigger compute_project_diff between parent and child
    db.lock_project(child_id)
    
    # Reload and verify revisions_json on the child project has the diffs recorded
    child_project = db.get_project(child_id)
    revisions = json.loads(child_project.revisions_json)
    assert len(revisions) == 1
    diffs = revisions[0]["changed_parameters"]
    
    # Diffs should contain design life, thickness, modulus changes
    params = {d["param"]: d for d in diffs}
    assert "Design Life (years)" in params
    assert params["Design Life (years)"]["old"] == "15"
    assert params["Design Life (years)"]["new"] == "20"
    
    assert "BC Thickness (mm)" in params
    assert params["BC Thickness (mm)"]["old"] == "40.0"
    assert params["BC Thickness (mm)"]["new"] == "50.0"

    assert "BC Modulus (MPa)" in params
    assert params["BC Modulus (MPa)"]["old"] == "3000.0"
    assert params["BC Modulus (MPa)"]["new"] == "3200.0"

def test_archive_package(db):
    """Call generate_project_archive and verify zip file contents (disclaimer, summary, logs)."""
    proj = db.create_project(work_name="Archive Project")
    proj_id = proj.id
    checklist_data = {
        "design_review": True,
        "input_verification": True,
        "traffic_verification": False,
        "reviewer_notes": "Ready for submission"
    }
    db.save_project_checklist(proj_id, "Approved for Submission", checklist_data)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_report = Path(tmpdir) / "test_report.docx"
        dummy_report.write_text("Dummy word report content")
        
        archive_zip = Path(tmpdir) / "submission.zip"
        generate_project_archive(db, proj_id, dummy_report, archive_zip)
        
        assert archive_zip.is_file()
        
        # Verify ZIP contents
        with zipfile.ZipFile(archive_zip, "r") as z:
            namelist = z.namelist()
            assert "README_Disclaimer.txt" in namelist
            assert "ProjectInputs.json" in namelist
            assert "CalculationSummary.txt" in namelist
            assert "ApprovalSheet.txt" in namelist
            assert "RevisionHistoryLog.json" in namelist
            assert "test_report.docx" in namelist
            
            disclaimer = z.read("README_Disclaimer.txt").decode("utf-8")
            assert "Submission package is decision-support documentation. Final field execution" in disclaimer
            assert "requires review and sign-off by a qualified pavement engineer" in disclaimer
            
            approval_sheet = z.read("ApprovalSheet.txt").decode("utf-8")
            assert "Design Review Completed             : [YES]" in approval_sheet
            assert "Traffic Assumptions Verified        : [NO]" in approval_sheet
            assert "Ready for submission" in approval_sheet

def test_dpr_layout(db):
    """Generate a docx combined report and verify presence of new Cover Page, Assumptions, Limitations, Checklists, and Signature blocks."""
    proj = db.create_project(work_name="DPR Project")
    proj_id = proj.id
    db.save_project_checklist(proj_id, "Approved for Submission", {"design_review": True})
    
    inp = StructuralInput(design_life_years=15, subgrade_cbr_pct=5.0)
    layers = (PavementLayer(name="BC", thickness_mm=40.0),)
    result = StructuralResult(inputs=inp, design_msa=10.0, growth_factor=1.2, subgrade_mr_mpa=50.0, composition=layers, total_pavement_thickness_mm=40.0)
    db.save_structural_design(project_id=proj_id, result=result)
    
    ctx = CombinedReportContext(
        project_title="Consultancy Pavement Design Study",
        work_name="DPR Project",
        client="State Highway Dept",
        submitted_by="Senior Pavement Consultant"
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = Path(tmpdir) / "DPR_Report.docx"
        out_path, included = build_combined_report(report_file, db, proj_id, ctx)
        
        assert report_file.is_file()
        assert "Assumptions Sheet" in included
        assert "Limitations Sheet" in included
        assert "Engineer Review Checklist" in included
        assert "Signature & Seal Placeholders" in included
        
        # Verify paragraph details
        doc = Document(report_file)
        full_text = "\n".join([para.text for para in doc.paragraphs])
        
        assert "ASSUMPTIONS SHEET" in full_text
        assert "LIMITATIONS OF THE REPORT" in full_text
        assert "ENGINEER REVIEW CHECKLIST" in full_text
        assert "ENGINEERING SIGN-OFF AND SEAL" in full_text
        assert "Signature of Reviewing Engineer" in full_text
