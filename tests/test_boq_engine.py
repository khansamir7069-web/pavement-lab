from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest

from app.db.repository import Database
from app.db.schema import (
    Project,
    StructuralDesign,
    StabilizedDesign,
    MechanisticValidation,
    MaterialQuantityDesign,
)
from app.engineering.boq_engine import (
    generate_boq,
    get_material_key,
    format_indian_currency,
    calculate_layer_boq,
)
from app.reports.excel_exporter import build_boq_excel
from app.reports.report_builder import build_combined_report, CombinedReportContext


@pytest.fixture
def temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="test_boq_")
    db_file = Path(tmpdir) / "test_boq.db"
    yield db_file


@pytest.fixture
def db(temp_db_path):
    database = Database(temp_db_path)
    yield database
    try:
        database.engine.dispose()
    except Exception:
        pass


def test_format_indian_currency():
    """Verify that formatting fits the Indian standard Lakh/Crore notation."""
    assert format_indian_currency(1234567.89) == "₹12.35 L"
    assert format_indian_currency(123456789.0) == "₹12.35 Cr"
    assert format_indian_currency(5000.0) == "₹5,000.00"


def test_get_material_key():
    """Verify mapping of layer names to standard material keys."""
    assert get_material_key("Bituminous Concrete (BC)") == "BC"
    assert get_material_key("Dense Bituminous Macadam") == "DBM"
    assert get_material_key("Wet Mix Macadam (WMM)") == "WMM"
    assert get_material_key("Granular Sub-base") == "GSB"
    assert get_material_key("CTB Layer") == "STABILIZED"
    assert get_material_key("CTS Layer") == "STABILIZED"
    assert get_material_key("Soil Subgrade") == "Aggregate"


def test_layer_boq_calculation():
    """Verify core layer volume, weight, and constituent tonnage calculations."""
    rates = {
        "BC": {"rate": 8500.0, "unit": "Tonne"},
        "GSB": {"rate": 1500.0, "unit": "Cum"},
        "Cement": {"rate": 7000.0, "unit": "Tonne"},
        "Aggregate": {"rate": 1200.0, "unit": "Tonne"},
    }

    # 1. Bituminous Layer (BC)
    res_bc = calculate_layer_boq("BC", 40.0, 1000.0, 7.0, rates)
    # Area = 7000, Vol = 7000 * 0.04 = 280 m3
    # Weight = 280 * 2.4 * 1.02 (waste) = 685.44 tonnes
    assert res_bc["volume_m3"] == pytest.approx(280.0)
    assert res_bc["weight_t"] == pytest.approx(685.44)
    # Bitumen = 685.44 * 5.5% = 37.6992 tonnes
    assert res_bc["bitumen_t"] == pytest.approx(37.6992)
    assert res_bc["cement_t"] == 0.0
    # Cost = 685.44 t * 8500 = 5,826,240
    assert res_bc["cost"] == pytest.approx(5826240.0)

    # 2. Granular Layer (GSB with rate in Cum)
    res_gsb = calculate_layer_boq("GSB", 150.0, 1000.0, 10.0, rates)
    # Area = 10000, Vol = 1500 m3
    assert res_gsb["volume_m3"] == pytest.approx(1500.0)
    # Cost = 1500 m3 * 1500/m3 = 2,250,000
    assert res_gsb["cost"] == pytest.approx(2250000.0)

    # 3. Cement Stabilized Layer (CTB)
    res_ctb = calculate_layer_boq("CTB", 100.0, 1000.0, 10.0, rates)
    # Area = 10000, Vol = 1000 m3
    # Weight = 1000 * 2.2 * 1.02 = 2244 tonnes
    # Cement = 2244 * 4.5% = 100.98 t
    # Aggregate = 2244 - 100.98 = 2143.02 t
    # Cost = 100.98 * 7000 + 2143.02 * 1200 = 706860 + 2571624 = 3278484
    assert res_ctb["cement_t"] == pytest.approx(100.98)
    assert res_ctb["aggregate_t"] == pytest.approx(2143.02)
    assert res_ctb["cost"] == pytest.approx(3278484.0)


def test_generate_boq_empty_project(db):
    """Verify that generate_boq handles empty projects gracefully."""
    proj = db.create_project(work_name="Empty Project Test")
    boq = generate_boq(proj.id, db)
    
    assert boq["available"] is False
    assert boq["show_rupees"] is False


def test_generate_boq_with_data(db):
    """Verify complete cost comparison when designs are present in DB."""
    proj = db.create_project(work_name="BOQ Integration Test")
    
    # 1. Structural Design (Option A)
    sd_composition = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "DBM", "thickness_mm": 80.0},
        {"name": "WMM", "thickness_mm": 250.0},
        {"name": "GSB", "thickness_mm": 150.0}
    ]
    # 2. Stabilized Design (Option B)
    stab_composition = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "CTB", "thickness_mm": 100.0},
        {"name": "CTS", "thickness_mm": 100.0}
    ]

    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            composition_json=json.dumps(sd_composition),
            total_pavement_thickness_mm=520.0
        )
        stab = StabilizedDesign(
            project_id=proj.id,
            inputs_json=json.dumps({"ctb_ucs_mpa": 4.5}),
            results_json=json.dumps({"stabilized_composition": stab_composition})
        )
        mv = MechanisticValidation(
            project_id=proj.id,
            fatigue_verdict="PASS",
            rutting_verdict="PASS"
        )
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json=json.dumps({
                "road_length_m": 2000.0,
                "carriageway_width_m": 7.0,
                "shoulder_width_m": 1.5,
                "layers": []
            })
        )
        s.add_all([sd, stab, mv, mq])
        s.commit()

    boq = generate_boq(proj.id, db)
    
    assert boq["available"] is True
    assert boq["show_rupees"] is True
    assert boq["road_length_m"] == 2000.0
    
    opts = boq["options"]
    assert opts["Option A"]["available"] is True
    assert opts["Option B"]["available"] is True
    assert opts["Option C"]["available"] is True
    assert opts["Option D"]["available"] is True
    
    # Option D should refer to Option C (Verified Pass + Stabilized savings)
    assert opts["Option D"]["selected_reference"] == "Option C"
    assert opts["Option D"]["total_cost"] == opts["Option C"]["total_cost"]


def test_excel_and_word_exporters_smoke(db):
    """Verify that build_boq_excel and combined report builder run cleanly without crashes."""
    proj = db.create_project(work_name="Exporter Smoke Test")
    
    sd_composition = [
        {"name": "BC", "thickness_mm": 40.0},
        {"name": "GSB", "thickness_mm": 150.0}
    ]

    with db.session() as s:
        sd = StructuralDesign(
            project_id=proj.id,
            composition_json=json.dumps(sd_composition),
            total_pavement_thickness_mm=190.0
        )
        mq = MaterialQuantityDesign(
            project_id=proj.id,
            inputs_json=json.dumps({
                "road_length_m": 1000.0,
                "carriageway_width_m": 7.0,
                "shoulder_width_m": 1.5,
                "layers": [{"layer_type": "BC", "length_m": 1000.0, "width_m": 7.0, "thickness_mm": 40.0, "waste_pct": 2.0}]
            })
        )
        s.add_all([sd, mq])
        s.commit()

    meta = {
        "work_name": "Test Highway",
        "client": "NHAI",
        "agency": "Contractor Co",
        "submitted_by": "Senior Consultant",
    }

    # Test Excel Export
    with tempfile.TemporaryDirectory() as tmpdir:
        excel_path = Path(tmpdir) / "test_boq.xlsx"
        build_boq_excel(excel_path, proj.id, db, meta)
        assert excel_path.exists()
        assert excel_path.stat().st_size > 0

    # Test Word Combined Export (includes write_cost_estimation_section)
    with tempfile.TemporaryDirectory() as tmpdir:
        word_path = Path(tmpdir) / "test_report.docx"
        
        ctx = CombinedReportContext(
            project_title="Combined Test",
            work_name="Combined Test Work",
            client="NHAI",
            agency="Test Agency",
            submitted_by="Engineer",
            report_date="2026-06-24",
        )
        
        build_combined_report(word_path, db, proj.id, ctx)
        assert word_path.exists()
        assert word_path.stat().st_size > 0
