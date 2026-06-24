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
)
from app.engineering.option_engine import generate_pavement_options
from app.reports.report_builder import build_combined_report, CombinedReportContext


@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_opt_")
    db_file = Path(tmpdir) / "test_opt.db"
    yield db_file


@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass


def test_empty_project_options(db):
    """Verify that an empty project returns safe/fallback option outputs without crashing."""
    proj = db.create_project(work_name="Empty Project Test")
    options = generate_pavement_options(proj.id, db)
    
    assert len(options) == 4
    
    # Assert all option structures have default keys
    for opt in options:
        assert "option_name" in opt
        assert "design_type" in opt
        assert "layers" in opt
        assert "thickness_summary" in opt
        assert "total_pavement_thickness" in opt
        assert "estimated_cost_indicator" in opt
        assert "engineering_score" in opt
        assert "iitpave_status" in opt
        assert "advantages" in opt
        assert "limitations" in opt
        assert "recommendation_reason" in opt
        
    # Check that for an empty project they all default to uncalculated or zero thickness
    assert options[0]["total_pavement_thickness"] == 0.0
    assert options[0]["layers"] == "No design computed"
    assert options[1]["total_pavement_thickness"] == 0.0
    assert options[1]["layers"] == "No design computed"
    assert options[2]["total_pavement_thickness"] == 0.0
    assert options[2]["layers"] == "No design computed"
    assert options[3]["total_pavement_thickness"] == 0.0
    assert options[3]["layers"] == "No design computed"


def test_conventional_option_generation(db):
    """Verify Option A (Conventional) is populated correctly when a StructuralDesign is present."""
    proj = db.create_project(work_name="Conventional Test")
    
    # Create structural design
    composition = [
        {"name": "BC", "thickness_mm": 40.0, "material": "BC"},
        {"name": "DBM", "thickness_mm": 80.0, "material": "DBM-II"},
        {"name": "WMM", "thickness_mm": 250.0, "material": "WMM"},
        {"name": "GSB", "thickness_mm": 150.0, "material": "GSB"}
    ]
    
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            composition_json=json.dumps(composition),
            total_pavement_thickness_mm=520.0,
            design_msa=10.0
        )
        s.add(sd)
        s.commit()

    options = generate_pavement_options(proj.id, db)
    
    # Check Option A
    opt_a = options[0]
    assert opt_a["design_type"] == "Conventional Flexible"
    assert opt_a["total_pavement_thickness"] == 520.0
    assert "BC (40 mm)" in opt_a["layers"]
    assert "DBM (80 mm)" in opt_a["layers"]
    assert opt_a["engineering_score"] == 75
    
    # Option B, C, D should remain fallback since no stabilized/verified design exists
    assert options[1]["total_pavement_thickness"] == 0.0
    assert options[2]["total_pavement_thickness"] == 0.0
    
    # Since only Option A is calculated, Option D should select Option A
    opt_d = options[3]
    assert opt_d["design_type"] == "Recommended Option"
    assert opt_d["total_pavement_thickness"] == 520.0
    assert "Conventional flexible pavement recommended" in opt_d["recommendation_reason"]



def test_stabilized_option_generation(db):
    """Verify Option B (Stabilized) is populated correctly when StabilizedDesign is present."""
    proj = db.create_project(work_name="Stabilized Test")
    
    # Create structural design first (so Option A is also present)
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            composition_json=json.dumps([{"name": "BC", "thickness_mm": 40.0}, {"name": "DBM", "thickness_mm": 80.0}]),
            total_pavement_thickness_mm=520.0,
            design_msa=10.0
        )
        s.add(sd)
        s.commit()
        
    # Create stabilized design
    stab_comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "CTB", "thickness_mm": 100.0},
        {"name": "GSB", "thickness_mm": 150.0}
    ]
    with db.session() as s:
        stab = StabilizedDesign(
            project_id=proj.id,
            inputs_json=json.dumps({"ctb_ucs_mpa": 4.5}),
            results_json=json.dumps({"stabilized_composition": stab_comp})
        )
        s.add(stab)
        s.commit()
        
    options = generate_pavement_options(proj.id, db)
    
    # Check Option B
    opt_b = options[1]
    assert opt_b["design_type"] == "Stabilized Pavement"
    assert opt_b["total_pavement_thickness"] == 290.0
    assert "CTB (100 mm)" in opt_b["layers"]
    assert opt_b["engineering_score"] == 85
    
    # Option D should select Option B because it is thinner (290 mm < 520 mm) and has valid UCS
    opt_d = options[3]
    assert opt_d["design_type"] == "Recommended Option"
    assert opt_d["total_pavement_thickness"] == 290.0
    assert "CTB/CTS alternative reduces granular thickness" in opt_d["recommendation_reason"]



def test_iitpave_verified_option_detection(db):
    """Verify Option C (Mechanistic Verified) is populated correctly when MechanisticValidation is PASS."""
    proj = db.create_project(work_name="IITPAVE Test")
    
    # Create structural and stabilized designs
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            composition_json=json.dumps([{"name": "BC", "thickness_mm": 40.0}]),
            total_pavement_thickness_mm=500.0
        )
        stab = StabilizedDesign(
            project_id=proj.id,
            inputs_json=json.dumps({"ctb_ucs_mpa": 4.5}),
            results_json=json.dumps({"stabilized_composition": [{"name": "BC", "thickness_mm": 40.0}, {"name": "CTB", "thickness_mm": 100.0}]})
        )
        s.add(sd)
        s.add(stab)
        s.commit()
        
    # Create mechanistic validation record
    with db.session() as s:
        mv = MechanisticValidation(
            project_id=proj.id,
            fatigue_verdict="PASS",
            rutting_verdict="PASS",
            summary_json=json.dumps({
                "fatigue": {"verdict": "PASS", "design_msa": 10.0},
                "rutting": {"verdict": "PASS", "design_msa": 10.0},
                "is_placeholder": False
            })
        )
        s.add(mv)
        s.commit()
        
    options = generate_pavement_options(proj.id, db)
    
    # Check Option C
    opt_c = options[2]
    assert opt_c["design_type"] == "Mechanistic Verified"
    assert "PASS" in opt_c["iitpave_status"]
    assert opt_c["engineering_score"] == 95
    
    # Option D should select Option C (Mechanistic Verified)
    opt_d = options[3]
    assert opt_d["design_type"] == "Recommended Option"
    assert opt_d["total_pavement_thickness"] == 140.0
    assert "IITPAVE verified stabilized design" in opt_d["recommendation_reason"]



def test_selected_option_persistence(db):
    """Verify that updating and saving selected option works and stores correctly."""
    proj = db.create_project(work_name="Selected Option Test")
    
    # Save selection
    db.update_selected_design_option(proj.id, "Option B: CTB/CTS Stabilized Pavement")
    
    # Fetch project back
    p = db.get_project(proj.id)
    assert p.selected_design_option == "Option B: CTB/CTS Stabilized Pavement"


def test_dpr_export_alternative_comparison(db):
    """Verify that combined DPR word report export succeeds with Pavement Alternative Comparison section."""
    proj = db.create_project(
        work_name="DPR Pavement Alternative Test",
        location="NH-2",
        road_category="NH / SH",
        highway_type="Expressway"
    )
    
    # Setup design data
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            inputs_json=json.dumps({
                "subgrade_cbr_pct": 5.0,
                "initial_cvpd": 2000.0,
                "growth_rate_pct": 7.5,
                "design_life_years": 15,
                "vdf": 2.5,
                "ldf": 0.75
            }),
            composition_json=json.dumps([
                {"name": "BC", "thickness_mm": 40.0},
                {"name": "DBM", "thickness_mm": 80.0},
                {"name": "WMM", "thickness_mm": 250.0},
                {"name": "GSB", "thickness_mm": 150.0}
            ]),
            total_pavement_thickness_mm=520.0
        )

        s.add(sd)
        s.commit()
        
    # Mark Option A as selected
    db.update_selected_design_option(proj.id, "Option A: Conventional Flexible Pavement")
    
    # Build report
    ctx = CombinedReportContext(
        client="Ministry of Road Transport",
        work_order_no="MORTH-2026-99",
        work_order_date="2026-01-15",
        report_date="2026-06-24"
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "dpr_report.docx"
        
        # This should execute successfully and write the PAVEMENT ALTERNATIVE COMPARISON section
        build_combined_report(out_file, db, proj.id, ctx=ctx)

        
        assert out_file.exists()
        assert out_file.stat().st_size > 0
