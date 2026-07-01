"""Unit tests for the validation parity report generator."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.validation.parity_models import ParityResult, ParitySummary
from mechanistic_solver.validation.parity_report import ParityReportGenerator


def test_parity_report_generation() -> None:
    """Verify Markdown and JSON report rendering and file saving."""
    res = ParityResult(
        case_id="case_report_1",
        roadx_outputs={"epsilon_t_bottom_bituminous": 120.0, "epsilon_v_top_subgrade": 230.0, "vertical_stress": 0.45, "deflection": 0.85},
        expected_outputs={"epsilon_t_bottom_bituminous": 120.0, "epsilon_v_top_subgrade": 240.0, "vertical_stress": 0.45, "deflection": 0.8},
        absolute_errors={"epsilon_t_bottom_bituminous": 0.0, "epsilon_v_top_subgrade": 10.0, "vertical_stress": 0.0, "deflection": 0.05},
        relative_errors={"epsilon_t_bottom_bituminous": 0.0, "epsilon_v_top_subgrade": 0.0416, "vertical_stress": 0.0, "deflection": 0.0625},
        pass_status={"epsilon_t_bottom_bituminous": True, "epsilon_v_top_subgrade": True, "vertical_stress": True, "deflection": False},
        overall_passed=False,
        warnings=["Parameter deflection failed parity"]
    )
    
    summary = ParitySummary(
        case_results=(res,),
        total_cases=1,
        passed_cases=0,
        failed_cases=1,
        overall_status="validated_case_fail",
        metrics={"epsilon_t_bottom_bituminous_mae": 0.0, "epsilon_t_bottom_bituminous_rmse": 0.0, "epsilon_v_top_subgrade_mae": 10.0, "epsilon_v_top_subgrade_rmse": 10.0, "vertical_stress_mae": 0.0, "vertical_stress_rmse": 0.0, "deflection_mae": 0.05, "deflection_rmse": 0.05},
        generation_timestamp="2026-06-30T12:00:00Z",
        warnings=["Case case_report_1: Parameter deflection failed parity"]
    )
    
    generator = ParityReportGenerator()
    
    # 1. Test Markdown generation
    md_report = generator.generate_markdown(summary)
    assert "# RoadX Multilayer Solver Parity Report" in md_report
    assert "VALIDATED_CASE_FAIL" in md_report
    assert "case_report_1" in md_report
    assert "deflection" in md_report.lower()
    
    # 2. Test JSON generation
    json_report = generator.generate_json(summary)
    data = json.loads(json_report)
    assert data["total_cases"] == 1
    assert data["overall_status"] == "validated_case_fail"
    
    # 3. Test saving to directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = generator.save_reports(summary, tmp_dir)
        
        assert os.path.exists(md_path)
        assert os.path.exists(json_path)
        
        assert Path(md_path).name == "parity_report.md"
        assert Path(json_path).name == "parity_report.json"
