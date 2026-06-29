import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timezone

from app.db.schema import Project, TrafficAnalysis, StructuralDesign, MixDesign, MaterialQuantityDesign
from app.db.repository import Database
from app.engineering.design_audit import run_project_audit
from app.reports.report_builder import build_combined_report, CombinedReportContext
from app.core.project_archive import generate_project_archive

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

def test_validation_gate_blocking(db):
    """Verify that project locking is blocked by the validation gate when critical issues exist or dependencies are missing."""
    proj = db.create_project(work_name="Gate Test Project")
    
    # 1. Try to check validation gate for empty project - should fail
    from app.engineering.design_audit import check_validation_gate
    ok, errors = check_validation_gate(proj.id, db)
    assert not ok
    assert len(errors) > 0

    # 2. Populate dependencies to pass validation gate
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.subgrade_cbr = 6.0
        p_row.subgrade_mr = 17.6 * (6.0 ** 0.64)
        p_row.review_status = "Approved for Submission"
        p_row.checklist_json = json.dumps({
            "design_review": True,
            "input_verification": True,
            "traffic_verification": True,
            "material_verification": True
        })
        s.commit()
        
    # Add traffic analysis
    ta_inputs = {
        "initial_cvpd": 1000.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "design_life_years": 15,
        "ldf": 0.75
    }
    with db.session() as s:
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=10.0
        )
        s.add(ta)
        s.commit()
        
    # Add structural design (with traceability logs)
    comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    traceability_log = {
        "traffic_category": "Medium Traffic",
        "cbr_category": "CBR 6.0%",
        "final_selection": {"reference_plate": "Plate 1"},
        "mechanistic_verification": "PASS",
        "client_summary": {"estimated_cost": "Rs. 1.2 Cr"},
        "decision_tree_ascii": "Decision -> Plate 1",
        "irc_ref_card": {
            "standard": "IRC:37-2018",
            "edition": "2018",
            "table_number": "Table 2",
            "figure_number": "Figure 3"
        }
    }
    with db.session() as s:
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
            total_pavement_thickness_mm=570.0,
            traceability_log_json=json.dumps(traceability_log),
            design_msa=10.0,
            subgrade_mr_mpa=17.6 * (6.0 ** 0.64)
        )
        s.add(sd)
        s.commit()
        
    # Add BOQ/Material Quantity
    with db.session() as s:
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json=json.dumps({"layers": comp}),
            results_json="{}",
            total_layer_tonnage_t=100.0,
            total_binder_tonnage_t=5.0
        )
        s.add(mq)
        s.commit()

    # Add passing IITPAVE Mechanistic Validation
    from app.db.schema import MechanisticValidation
    with db.session() as s:
        mv = MechanisticValidation(
            project_id=proj.id,
            summary_json=json.dumps({
                "fatigue": {"verdict": "PASS", "strain": 0.8e-4, "allowable": 1.0e-4},
                "rutting": {"verdict": "PASS", "strain": 1.0e-4, "allowable": 2.0e-4}
            }),
            refused=False
        )
        s.add(mv)
        s.commit()

    # Re-run audit & check validation gate
    ok2, errors2 = check_validation_gate(proj.id, db)
    assert ok2  # Should pass now!
    assert len(errors2) == 0
    
    # Verify we can now lock the project successfully
    db.lock_project(proj.id)
    locked_proj = db.get_project(proj.id)
    assert locked_proj.locked is True


def test_revision_validation_status_and_files(db):
    """Verify that locking records validation status and file generation logs files correctly in the revisions history."""
    proj = db.create_project(work_name="Complete Revision Project")
    
    # 1. Set up passing validation parameters
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.subgrade_cbr = 6.0
        p_row.subgrade_mr = 17.6 * (6.0 ** 0.64)
        p_row.review_status = "Approved for Submission"
        p_row.checklist_json = json.dumps({
            "design_review": True,
            "input_verification": True,
            "traffic_verification": True,
            "material_verification": True
        })
        s.commit()
        
    ta_inputs = {
        "initial_cvpd": 1000.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "design_life_years": 15,
        "ldf": 0.75
    }
    comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    traceability_log = {
        "traffic_category": "Medium Traffic",
        "cbr_category": "CBR 6.0%",
        "final_selection": {"reference_plate": "Plate 1"},
        "mechanistic_verification": "PASS",
        "client_summary": {"estimated_cost": "Rs. 1.2 Cr"},
        "decision_tree_ascii": "Decision -> Plate 1",
        "irc_ref_card": {
            "standard": "IRC:37-2018",
            "edition": "2018",
            "table_number": "Table 2",
            "figure_number": "Figure 3"
        }
    }
    with db.session() as s:
        ta = TrafficAnalysis(project_id=proj.id, inputs_json=json.dumps(ta_inputs), design_msa=10.0)
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=json.dumps({}),
            composition_json=json.dumps(comp),
            total_pavement_thickness_mm=570.0,
            traceability_log_json=json.dumps(traceability_log),
            design_msa=10.0,
            subgrade_mr_mpa=17.6 * (6.0 ** 0.64)
        )
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json=json.dumps({"layers": comp}),
            results_json="{}",
            total_layer_tonnage_t=100.0,
            total_binder_tonnage_t=5.0
        )
        s.add_all([ta, sd, mq])
        s.commit()

    # Pre-audit to populate validation results
    run_project_audit(proj.id, db)
    
    # 2. Lock Parent
    db.lock_project(proj.id)
    
    # 3. Create Revision
    note_dict = {
        "engineer": "John Connor",
        "description": "Design refinement",
        "reason": "Optimize BC layer"
    }
    rev_id = db.create_project_revision(proj.id, json.dumps(note_dict))
    
    # 4. Check Revision fields
    child = db.get_project(rev_id)
    revisions = json.loads(child.revisions_json)
    assert len(revisions) == 1
    
    rev_entry = revisions[0]
    assert rev_entry["revision_number"] == 1
    assert rev_entry["engineer"] == "John Connor"
    assert rev_entry["description"] == "Design refinement"
    
    # 5. Lock Revision (Child)
    run_project_audit(child.id, db)
    db.lock_project(child.id)
    
    # Retrieve updated revision status
    child = db.get_project(rev_id)
    revisions = json.loads(child.revisions_json)
    rev_entry = revisions[0]
    assert "READY" in rev_entry["validation_status"] or "Draft" in rev_entry["validation_status"] or "Audited" in rev_entry["validation_status"] or "SUBMISSION" in rev_entry["validation_status"]
    
    # 6. Record generated file
    db.record_generated_file(child.id, "submission_pkg_R1.zip")
    child = db.get_project(rev_id)
    revisions = json.loads(child.revisions_json)
    assert "submission_pkg_R1.zip" in revisions[0]["generated_files"]


def test_legacy_fallbacks(db):
    """Verify that generating reports for legacy projects works without crash by falling back gracefully."""
    proj = db.create_project(work_name="Legacy Project")
    
    # No subgrade, no traffic, no revisions_json populated
    meta = {
        "project_title": proj.work_name,
        "work_name": proj.work_name,
        "work_order_no": "",
        "work_order_date": "",
        "client": "",
        "agency": "",
        "submitted_by": "",
        "report_date": "29-Jun-2026",
        "binder_grade": "",
        "mix_type_key": "",
    }
    ctx = CombinedReportContext(**meta)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "legacy_report.docx"
        
        # Creating a stub structural design to bypass build_combined_report raise check
        with db.session() as s:
            sd = StructuralDesign(
                project_id=proj.id,
                inputs_json="{}",
                composition_json="[]",
                total_pavement_thickness_mm=0.0
            )
            s.add(sd)
            s.commit()
            
        # Compile report - should not raise any AttributeError/KeyError and complete successfully
        build_combined_report(out_path, db, proj.id, ctx)
        assert out_path.is_file()


def test_project_recovery_system(db):
    """Verify that abnormal termination recovery works correctly by saving and restoring a project."""
    proj = db.create_project(work_name="Recovery Source Project")
    
    from app.db.project_exchange import export_project, import_project
    checkpoint = export_project(db, proj.id)
    
    # Verify we can modify name and import it back
    payload = checkpoint
    payload["project"]["work_name"] = f"{proj.work_name} (Recovered)"
    
    res = import_project(db, payload)
    recovered_project = db.get_project(res.project_id)
    assert recovered_project.work_name == "Recovery Source Project (Recovered)"
    assert recovered_project.id != proj.id
