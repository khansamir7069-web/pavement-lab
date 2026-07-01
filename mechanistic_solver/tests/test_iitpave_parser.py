"""Unit tests for the IITPAVE output parser."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from mechanistic_solver.validation.iitpave_parser import IITPAVEOutputParser


def test_parse_sample_iitpave_output() -> None:
    """Verify that the parser correctly reads a sample IITPAVE output file."""
    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "iitpave"
    out_path = fixtures_dir / "sample_iitpave_output.out"
    json_path = fixtures_dir / "sample_iitpave_expected.json"
    
    assert out_path.exists()
    assert json_path.exists()
    
    with open(out_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
        
    with open(json_path, "r", encoding="utf-8") as f:
        expected = json.load(f)
        
    parser = IITPAVEOutputParser()
    # Parse with specific bituminous and subgrade depths matching the fixture depths (40.0 and 190.0)
    parsed = parser.parse(raw_text, source_file=str(out_path), bituminous_depth_mm=40.0, subgrade_depth_mm=190.0)
    
    assert parsed.parse_status == "success"
    assert parsed.source_file == "sample_iitpave_output.out"
    assert parsed.raw_text == raw_text
    
    # Check critical response extraction
    crit = parsed.critical_responses
    # expected has microstrains: eps_t = 200, eps_v = 250
    assert crit["epsilon_t_bottom_bituminous"] == pytest.approx(expected["critical_responses"]["epsilon_t_bottom_bituminous"])
    assert crit["epsilon_v_top_subgrade"] == pytest.approx(expected["critical_responses"]["epsilon_v_top_subgrade"])
    assert crit["vertical_stress"] == pytest.approx(expected["critical_responses"]["vertical_stress"])
    assert crit["deflection"] == pytest.approx(expected["critical_responses"]["deflection"])
    
    # Check layer response rows count
    assert len(parsed.layer_responses) == len(expected["layer_responses"])
    for idx, row in enumerate(parsed.layer_responses):
        exp_row = expected["layer_responses"][idx]
        assert row["z"] == pytest.approx(exp_row["z"])
        assert row["r"] == pytest.approx(exp_row["r"])
        assert row["sigma_z"] == pytest.approx(exp_row["sigma_z"])
        assert row["epsilon_z"] == pytest.approx(exp_row["epsilon_z"])


def test_parser_missing_fields_and_tables() -> None:
    """Verify parser returns None and records warnings for missing or unparseable input."""
    parser = IITPAVEOutputParser()
    
    # Empty raw text
    parsed_empty = parser.parse("", source_file="empty.out")
    assert parsed_empty.parse_status == "failed"
    assert parsed_empty.critical_responses["epsilon_t_bottom_bituminous"] is None
    
    # Output missing Z and R table headers
    bad_table_text = "Some random text description\n1.0 2.0 3.0 4.0"
    parsed_bad = parser.parse(bad_table_text)
    assert parsed_bad.parse_status == "failed"
    assert len(parsed_bad.layer_responses) == 0
    assert any("critical responses" in w.lower() for w in parsed_bad.warnings)
