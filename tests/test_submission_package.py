from __future__ import annotations

import json
import tempfile
import zipfile
import pytest
from pathlib import Path
from datetime import datetime, timezone

from app.db.repository import Database
from app.db.schema import (
    Project,
    StructuralDesign,
    MechanisticValidation,
    MaterialQuantityDesign,
    TrafficAnalysis,
)
from app.core.branding import get_branding_profile, save_branding_profile
from app.reports.report_builder import build_combined_report, CombinedReportContext
from app.core.project_archive import generate_project_archive


@pytest.fixture
def backup_branding():
    """Backup active branding profile and restore it after tests run."""
    from app.core.branding import BRANDING_FILE
    backup_path = BRANDING_FILE.with_suffix(".json.bak")
    has_backup = False
    if BRANDING_FILE.is_file():
        try:
            BRANDING_FILE.rename(backup_path)
            has_backup = True
        except Exception:
            pass
    yield
    if has_backup:
        try:
            if BRANDING_FILE.is_file():
                BRANDING_FILE.unlink()
            backup_path.rename(BRANDING_FILE)
        except Exception:
            pass
    elif BRANDING_FILE.is_file():
        try:
            BRANDING_FILE.unlink()
        except Exception:
            pass


@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_submission_")
    db_file = Path(tmpdir) / "test_submission.db"
    yield db_file


@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass


def test_branding_profile_save_load(backup_branding):
    """Verify saving and loading the branding profile settings."""
    profile_data = {
        "company_name": "Test Consultants Ltd",
        "logo_path": "C:/fake/path/logo.png",
        "address": "123 Pavement Street",
        "contact": "info@test.com",
        "engineer_name": "John Doe, PE",
        "registration_number": "REG-12345"
    }
    save_branding_profile(profile_data)
    
    loaded = get_branding_profile()
    assert loaded["company_name"] == "Test Consultants Ltd"
    assert loaded["logo_path"] == "C:/fake/path/logo.png"
    assert loaded["address"] == "123 Pavement Street"
    assert loaded["contact"] == "info@test.com"
    assert loaded["engineer_name"] == "John Doe, PE"
    assert loaded["registration_number"] == "REG-12345"


def test_branding_optional_registration(backup_branding):
    """Verify that blank registration number is optional and defaults are maintained."""
    profile_data = {
        "company_name": "Test Consultants Ltd",
        "logo_path": "",
        "address": "",
        "contact": "",
        "engineer_name": "Jane Doe",
        "registration_number": ""  # blank
    }
    save_branding_profile(profile_data)
    
    loaded = get_branding_profile()
    assert loaded["engineer_name"] == "Jane Doe"
    assert loaded["registration_number"] == ""


def test_missing_logo_does_not_crash_report(db, tmp_path, backup_branding):
    """Verify that compiling Word report does not crash when branding logo is missing or invalid."""
    proj = db.create_project(
        work_name="Logo Test Project",
        subgrade_cbr=5.0
    )
    
    # Save basic structural design to make it exportable
    comp = [{"name": "GSB", "thickness_mm": 150.0}]
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json="{}",
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=150.0
        )
        s.add(sd)
        s.commit()

    # Save branding with missing logo path
    profile_data = {
        "company_name": "No Logo Inc",
        "logo_path": "C:/non_existent_directory/non_existent_logo.png",
        "address": "",
        "contact": "",
        "engineer_name": "A. Engineer",
        "registration_number": ""
    }
    save_branding_profile(profile_data)

    ctx = CombinedReportContext(
        project_title="Logo Test Title",
        work_name="Logo Test Work",
        client="Logo Test Client"
    )
    
    out_file = tmp_path / "logo_test_report.docx"
    
    # Report compilation should succeed without throwing exceptions about the missing logo file
    path, included = build_combined_report(out_file, db, proj.id, ctx)
    assert path.exists()


def test_submission_package_generation(db, tmp_path, backup_branding):
    """Verify ZIP package is compiled with the exact folder layout and legacy root compatibility."""
    proj = db.create_project(
        work_name="Submission Package Test Project",
        subgrade_cbr=5.0
    )
    
    # Save basic structural design
    comp = [{"name": "BC", "thickness_mm": 40.0}]
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json="{}",
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=40.0
        )
        # Add traffic analysis
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json="{}",
            design_msa=10.0
        )
        s.add(sd)
        s.add(ta)
        s.commit()

    # Save branding
    profile_data = {
        "company_name": "Archive Consultants",
        "logo_path": "",
        "address": "",
        "contact": "",
        "engineer_name": "Lead Engineer",
        "registration_number": "PE-999"
    }
    save_branding_profile(profile_data)

    ctx = CombinedReportContext(
        project_title="Submission Test Title",
        work_name="Submission Test Work",
        client="Submission Test Client"
    )
    
    report_file = tmp_path / "combined_report.docx"
    build_combined_report(report_file, db, proj.id, ctx)
    
    archive_out_file = tmp_path / "submission_package.zip"
    
    # Generate package
    generate_project_archive(db, proj.id, report_file, archive_out_file)
    
    assert archive_out_file.exists()
    
    # Open and verify ZIP layout
    with zipfile.ZipFile(archive_out_file, "r") as zf:
        namelist = zf.namelist()
        
        # Verify new Phase 5 structured package folders
        assert "Reports/Professional_DPR.docx" in namelist
        assert "Reports/BOQ_Estimate.xlsx" in namelist
        assert "Reports/Audit_Report.txt" in namelist
        assert "Design/Input_Data.xlsx" in namelist
        assert "Design/Layer_Summary.xlsx" in namelist
        assert "IITPAVE/Run_Log.txt" in namelist
        assert "IITPAVE/Verification_Report.txt" in namelist
        assert "Archive/Revision_History.txt" in namelist
        
        # Verify legacy root compatibility files
        assert "README_Disclaimer.txt" in namelist
        assert "ProjectInputs.json" in namelist
        assert "CalculationSummary.txt" in namelist
        assert "ApprovalSheet.txt" in namelist
        assert "RevisionHistoryLog.json" in namelist
        assert "combined_report.docx" in namelist  # name of the passed in report file at root


def test_fail_safe_zip_generation_missing_iitpave(db, tmp_path):
    """Verify that if IITPAVE log/verification file is missing, ZIP compilation succeeds with placeholder."""
    # Mock get_last_run_info to return None to ensure we test the fallback behavior
    import app.core.project_archive as pa
    original_get_last_run_info = pa.get_last_run_info
    try:
        pa.get_last_run_info = lambda: None
        
        proj = db.create_project(work_name="No IITPAVE Test Project")
        
        report_file = tmp_path / "dummy_report.docx"
        report_file.write_text("dummy report content")
        
        archive_out_file = tmp_path / "submission_package_no_iitpave.zip"
        
        # Generate archive
        generate_project_archive(db, proj.id, report_file, archive_out_file)
        
        assert archive_out_file.exists()
        
        with zipfile.ZipFile(archive_out_file, "r") as zf:
            namelist = zf.namelist()
            assert "IITPAVE/Run_Log.txt" in namelist
            assert "IITPAVE/Verification_Report.txt" in namelist
            
            # Check contents for placeholders
            run_log_content = zf.read("IITPAVE/Run_Log.txt").decode("utf-8")
            verif_content = zf.read("IITPAVE/Verification_Report.txt").decode("utf-8")
            
            assert "IITPAVE verification file not available." in run_log_content
            assert "IITPAVE verification file not available." in verif_content
    finally:
        pa.get_last_run_info = original_get_last_run_info


def test_revision_serialization_and_parsing(db):
    """Verify revision note details (engineer, description, reason) serialize to JSON and parse correctly."""
    proj = db.create_project(
        work_name="Revision Test Project",
        review_status="Approved for Submission",
        locked=True
    )
    
    note_dict = {
        "engineer": "Sarah Conner",
        "description": "Checked structural layers against field soil testing report",
        "reason": "Regulatory requirement compliance check"
    }
    note_str = json.dumps(note_dict)
    
    # Create revision
    rev_pid = db.create_project_revision(proj.id, note_str)
    
    # Retrieve revision child
    child = db.get_project(rev_pid)
    assert child.revisions_json is not None
    
    revisions = json.loads(child.revisions_json)
    assert len(revisions) == 1
    
    entry = revisions[0]
    assert entry["revision_number"] == 1
    
    parsed_note = json.loads(entry["engineer_note"])
    assert parsed_note["engineer"] == "Sarah Conner"
    assert parsed_note["description"] == "Checked structural layers against field soil testing report"
    assert parsed_note["reason"] == "Regulatory requirement compliance check"
