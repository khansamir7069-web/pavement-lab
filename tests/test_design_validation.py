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
    MixDesign,
    MaterialQuantityDesign,
)
from app.engineering.design_audit import run_project_audit, VALIDATION_CONFIG


@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_val_")
    db_file = Path(tmpdir) / "test_val.db"
    yield db_file


@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass


def test_engineering_validation_complete_safety(db):
    # Create project
    proj = db.create_project(work_name="Engineering Validation Safe Test")
    
    # 1. Traffic Analysis
    ta_inputs = {
        "initial_cvpd": 2000.0,
        "growth_rate_pct": 7.5,
        "vdf": 4.5,
        "lane_distribution_factor": 0.75,
        "design_life_years": 20
    }
    with db.session() as s:
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=45.0
        )
        s.add(ta)
        s.commit()

    # 2. Subgrade
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.subgrade_cbr = 8.0
        p_row.subgrade_mr = 17.6 * (8.0 ** 0.64)  # mr ~ 66.5 MPa
        s.commit()

    # 3. Structural Design
    sd_comp = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 100.0},
        {"name": "WMM", "thickness_mm": 150.0},
        {"name": "GSB", "thickness_mm": 200.0}
    ]
    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            design_msa=45.0,
            subgrade_mr_mpa=17.6 * (8.0 ** 0.64),
            total_pavement_thickness_mm=490.0,
            composition_json=json.dumps(sd_comp),
            traceability_log_json=json.dumps({"steps": ["Step 1", "Step 2"]})
        )
        s.add(sd)
        s.commit()

    # 4. IITPAVE Validation
    mv_summary = {
        "fatigue": {"verdict": "PASS"},
        "rutting": {"verdict": "PASS"}
    }
    with db.session() as s:
        mv = MechanisticValidation(
            project_id=proj.id,
            summary_json=json.dumps(mv_summary),
            fatigue_verdict="PASS",
            rutting_verdict="PASS",
            refused=False
        )
        s.add(mv)
        s.commit()

    # 5. Mix Design
    mix_res = {
        "stability_kn": 12.5,
        "flow_mm": 3.2,
        "air_voids_pct": 4.0,
        "obc_pct": 5.2
    }
    with db.session() as s:
        mix = MixDesign(
            project_id=proj.id,
            obc_pct=5.2,
            stability_at_obc_kn=12.5,
            flow_at_obc_mm=3.2,
            air_voids_at_obc_pct=4.0
        )
        s.add(mix)
        s.commit()

    # 6. BOQ
    mq_inputs = {
        "road_length_m": 1000.0,
        "carriageway_width_m": 7.0,
        "shoulder_width_m": 1.5,
        "layers": [
            {"layer_type": "BC", "thickness_mm": 40.0, "length_m": 1000.0, "width_m": 7.0},
            {"layer_type": "DBM", "thickness_mm": 100.0, "length_m": 1000.0, "width_m": 7.0},
            {"layer_type": "WMM", "thickness_mm": 150.0, "length_m": 1000.0, "width_m": 10.0},
            {"layer_type": "GSB", "thickness_mm": 200.0, "length_m": 1000.0, "width_m": 10.0}
        ]
    }
    with db.session() as s:
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json=json.dumps(mq_inputs),
            total_layer_tonnage_t=1000.0
        )
        s.add(mq)
        s.commit()

    # 7. Checklists
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.locked = True
        p_row.checklist_json = json.dumps({
            "design_review": True,
            "input_verification": True,
            "traffic_verification": True,
            "material_verification": True
        })
        s.commit()

    # Run validation audit
    res = run_project_audit(proj.id, db)

    # Asserts
    assert res.completeness_score == 100
    assert res.consistency_score == 100
    assert res.mechanistic_score == 100
    assert res.final_recommendation == "READY FOR CONSULTANCY SUBMISSION"
    assert res.score >= 90


def test_validation_manual_override_handling(db):
    proj = db.create_project(work_name="Manual Override Test")
    
    # Set Growth rate out of limits (e.g. 1.5% which is lower than min 2.0%)
    ta_inputs = {
        "initial_cvpd": 2000.0,
        "growth_rate_pct": 1.5,
        "vdf": 4.5,
        "lane_distribution_factor": 0.75,
        "design_life_years": 20
    }
    # Add manual override record
    overrides = [
        {
            "field_name": "growth_rate_pct",
            "original_value": 7.5,
            "new_value": 1.5,
            "reason": "Regional local traffic survey records low growth.",
            "timestamp": "2026-06-28",
            "module": "traffic"
        }
    ]
    with db.session() as s:
        p_row = s.get(Project, proj.id)
        p_row.override_history_json = overrides
        p_row.subgrade_cbr = 6.0
        p_row.subgrade_mr = 60.0
        s.commit()
        
        ta = TrafficAnalysis(
            project_id=proj.id,
            inputs_json=json.dumps(ta_inputs),
            design_msa=15.0
        )
        s.add(ta)
        s.commit()

    # Run validation audit
    res = run_project_audit(proj.id, db)
    
    # Verify that the growth rate is classified as a warning, not critical
    growth_finding = [f for f in res.findings if f.module == "traffic" and "Growth rate" in f.issue]
    assert len(growth_finding) == 1
    assert growth_finding[0].severity == "warning"
    assert "accepted via Manual Override" in growth_finding[0].issue
