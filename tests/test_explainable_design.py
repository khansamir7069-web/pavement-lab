import json
import pytest
from app.core import StructuralInput, StructuralResult, PavementLayer
from app.core.structural_design import compute_structural_design
from app.core.explainable_design import (
    generate_explainable_details,
    calculate_confidence_score,
    estimate_composition_cost,
    check_mechanistic_consistency
)
from app.reports.structural_report import write_explainability_sections
from docx import Document

def test_explainable_details_generation():
    # 1. Arrange
    inp = StructuralInput(
        road_category="NH / SH",
        design_life_years=15,
        initial_cvpd=2000,
        growth_rate_pct=7.5,
        vdf=3.5,
        ldf=0.75,
        subgrade_cbr_pct=5.0
    )
    
    # 2. Act
    res = compute_structural_design(inp)
    assert res.traceability_log_json is not None
    
    log = json.loads(res.traceability_log_json)
    
    # 3. Assert Decisions
    assert "High Traffic" in log["traffic_category"]
    assert "CBR 5%" in log["cbr_category"]
    assert log["confidence_score"] > 0
    assert len(log["candidates"]) > 0
    assert len(log["layer_justifications"]) > 0
    assert "standard" in log["irc_ref_card"]

def test_irc_reference_fallback():
    # Test fallback plate (e.g. out of range/Skeleton)
    inp = StructuralInput(
        road_category="MDR",
        design_life_years=10,
        initial_cvpd=10,  # extremely low
        growth_rate_pct=5.0,
        vdf=1.5,
        ldf=0.5,
        subgrade_cbr_pct=2.0  # CBR < 3% leads to Skeleton
    )
    res = compute_structural_design(inp)
    log = json.loads(res.traceability_log_json)
    
    assert "Reference unavailable" in log["irc_ref_card"]["table_number"]
    assert "Reference unavailable" in log["irc_ref_card"]["figure_number"]
    assert "Reference unavailable" in log["irc_ref_card"]["plate_number"]

def test_candidate_comparison_and_why_not():
    inp = StructuralInput(
        road_category="NH / SH",
        design_life_years=15,
        initial_cvpd=3000,
        subgrade_cbr_pct=5.0
    )
    res = compute_structural_design(inp)
    log = json.loads(res.traceability_log_json)
    
    candidates = log["candidates"]
    rejected = log["rejected_options"]
    
    # Verify we have candidates
    assert len(candidates) > 0
    
    # Since design traffic is high, lower-MSA options must be rejected
    assert len(rejected) > 0
    for rej in rejected:
        assert "Rejected:" in rej["reason"]

def test_layer_justification():
    layers = [
        PavementLayer("BC", 40.0, "BC"),
        PavementLayer("DBM", 100.0, "DBM"),
        PavementLayer("WMM", 250.0, "WMM"),
        PavementLayer("GSB", 150.0, "GSB")
    ]
    inp = StructuralInput()
    res = StructuralResult(inp, 10.0, 15.0, 50.0, tuple(layers), 540.0)
    
    log = generate_explainable_details(res, db=None, project_id=None)
    justs = log["layer_justifications"]
    
    assert len(justs) == 4
    assert "surface course" in justs[0]["reason"].lower()
    assert "fatigue" in justs[1]["reason"].lower()
    assert "base course" in justs[2]["reason"].lower()
    assert "foundation" in justs[3]["reason"].lower()

def test_confidence_score_breakdown():
    inp = StructuralInput()
    res = StructuralResult(inp, 10.0, 15.0, 50.0, (), 0.0)
    
    score, breakdown = calculate_confidence_score(res, db=None, project_id=None)
    
    assert score > 0.0
    assert "Traffic Input Quality (20% weight)" in breakdown
    assert "Subgrade Quality (20% weight)" in breakdown
    assert "Catalogue Compliance (20% weight)" in breakdown

def test_report_graceful_fallback():
    # If traceability_log_json is None
    inp = StructuralInput()
    res = StructuralResult(inp, 10.0, 15.0, 50.0, (), 0.0, traceability_log_json=None)
    
    doc = Document()
    # Should not raise exception
    write_explainability_sections(doc, res)
    
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Traceability log not available for this legacy record" in text

def test_mechanistic_consistency():
    cat = [PavementLayer("BC", 40.0), PavementLayer("DBM", 80.0)]
    final = [PavementLayer("BC", 40.0), PavementLayer("DBM", 100.0)]
    
    lbl, desc = check_mechanistic_consistency(cat, final)
    assert lbl == "Minor Difference"
    assert "delta of 20 mm" in desc
