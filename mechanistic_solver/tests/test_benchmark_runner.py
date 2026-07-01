"""Unit tests for benchmark database ingestion, runner, statistics, diagnostics, and reporting."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.validation.benchmark_database import BenchmarkDatabase
from mechanistic_solver.validation.benchmark_runner import BenchmarkRunner
from mechanistic_solver.validation.benchmark_statistics import BenchmarkStatistics
from mechanistic_solver.validation.calibration_report import CalibrationReportGenerator
from mechanistic_solver.validation.parity_models import ParityCase
from mechanistic_solver.validation.benchmark_database import BenchmarkCase


@pytest.fixture
def temp_benchmark_dir() -> str:
    """Creates a temporary benchmark directory structure with varied test cases."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. Valid template case
        valid_json = {
            "inputs": {
                "layers": [
                    {"name": "Layer1", "thickness": 100.0, "elastic_modulus": 3000.0, "poisson_ratio": 0.35, "density": 2400.0}
                ],
                "subgrade": {"name": "Subgrade", "thickness": None, "elastic_modulus": 60.0, "poisson_ratio": 0.4, "density": 1800.0},
                "loads": [{"wheel_load": 39.58, "pressure": 0.56, "radius": 150.0}]  # Consistent: 0.56 * pi * 150^2 / 1000 = 39.58
            },
            "observation_points": [{"x": 0.0, "y": 0.0, "z": 100.0}],
            "expected_iitpave_outputs": {
                "tensile_strain_microstrain": 120.0,
                "vertical_strain_microstrain": 220.0,
                "vertical_stress_mpa": 0.45,
                "deflection_mm": 0.85
            },
            "notes": "Valid template case"
        }
        with open(tmp_path / "case_valid_template.json", "w", encoding="utf-8") as f:
            json.dump(valid_json, f)
            
        # Match with a simple output file
        valid_out = (
            "IITPAVE OUTPUT\n"
            "Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR\n"
            "100.0 0.0 0.45 0.15 0.15 0.0 0.85 -0.000220 0.000120 0.000120\n"
        )
        with open(tmp_path / "case_valid_template.out", "w", encoding="utf-8") as f:
            f.write(valid_out)

        # 2. Corrupt JSON case
        with open(tmp_path / "case_corrupt.json", "w", encoding="utf-8") as f:
            f.write("{invalid json content}")

        # 3. Official directory structure
        off_path = tmp_path / "official"
        off_path.mkdir()
        
        # Valid official case
        off_json = dict(valid_json)
        off_json["notes"] = "Valid official case"
        with open(off_path / "case_valid_official.json", "w", encoding="utf-8") as f:
            json.dump(off_json, f)
        with open(off_path / "case_valid_official.out", "w", encoding="utf-8") as f:
            f.write(valid_out)

        # Official case missing output
        with open(off_path / "case_missing_out.json", "w", encoding="utf-8") as f:
            json.dump(valid_json, f)
            
        # 4. Case with simulated unit mismatch
        unit_mismatch_json = dict(valid_json)
        unit_mismatch_json["expected_iitpave_outputs"] = {
            "deflection_mm": 0.00085
        }
        with open(tmp_path / "case_unit_mismatch.json", "w", encoding="utf-8") as f:
            json.dump(unit_mismatch_json, f)
        
        # Write matching mismatch output file
        unit_mismatch_out = (
            "IITPAVE OUTPUT\n"
            "Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR\n"
            "100.0 0.0 0.45 0.15 0.15 0.0 0.00085 -0.000220 0.000120 0.000120\n"
        )
        with open(tmp_path / "case_unit_mismatch.out", "w", encoding="utf-8") as f:
            f.write(unit_mismatch_out)
            
        # 5. Case with simulated radius mismatch (inconsistent load inputs)
        radius_mismatch_json = dict(valid_json)
        radius_mismatch_json["inputs"]["loads"] = [{"wheel_load": 80.0, "pressure": 0.56, "radius": 150.0}]
        with open(tmp_path / "case_radius_mismatch.json", "w", encoding="utf-8") as f:
            json.dump(radius_mismatch_json, f)
        with open(tmp_path / "case_radius_mismatch.out", "w", encoding="utf-8") as f:
            f.write(valid_out)

        yield str(tmp_path)


def test_benchmark_discovery_and_indexing(temp_benchmark_dir: str) -> None:
    """Verify BenchmarkDatabase discovers case files, indexes them, and handles errors gracefully."""
    db = BenchmarkDatabase(temp_benchmark_dir)
    cases = db.discover_cases()
    
    # We should have 6 cases discovered
    assert len(cases) == 6
    
    # Check parse statuses
    corrupt = next(c for c in cases if c.case_id == "case_corrupt")
    assert corrupt.parse_status == "corrupt_json"
    assert corrupt.parity_case is None
    
    missing = next(c for c in cases if c.case_id == "case_missing_out")
    assert missing.parse_status == "missing_out"
    assert missing.parity_case is not None
    assert missing.is_official is True
    
    valid_off = next(c for c in cases if c.case_id == "case_valid_official")
    assert valid_off.parse_status == "success"
    assert valid_off.is_official is True
    
    valid_temp = next(c for c in cases if c.case_id == "case_valid_template")
    assert valid_temp.parse_status == "success"
    assert valid_temp.is_official is False


def test_benchmark_runner_statuses(temp_benchmark_dir: str) -> None:
    """Verify that BenchmarkRunner correctly assigns execution statuses for batch cases."""
    db = BenchmarkDatabase(temp_benchmark_dir)
    cases = db.discover_cases()
    
    runner = BenchmarkRunner()
    results = runner.run_batch(cases)
    
    # Verify status mapping
    corrupt_rec = next(r for r in results if r["case_id"] == "case_corrupt")
    assert corrupt_rec["status"] == "corrupt_case"
    
    missing_rec = next(r for r in results if r["case_id"] == "case_missing_out")
    assert missing_rec["status"] == "skipped_missing_official_output"
    
    valid_off_rec = next(r for r in results if r["case_id"] == "case_valid_official")
    assert valid_off_rec["status"] in ["validated_case_pass", "validated_case_fail"]
    
    valid_temp_rec = next(r for r in results if r["case_id"] == "case_valid_template")
    assert valid_temp_rec["status"] in ["template_case_pass", "template_case_fail"]


def test_benchmark_statistics_computation(temp_benchmark_dir: str) -> None:
    """Verify statistical metrics aggregation behaves correctly."""
    db = BenchmarkDatabase(temp_benchmark_dir)
    cases = db.discover_cases()
    
    runner = BenchmarkRunner()
    results = runner.run_batch(cases)
    
    stats_agg = BenchmarkStatistics()
    summary_report = stats_agg.aggregate(results)
    
    assert "summary" in summary_report
    assert "global_metrics" in summary_report
    assert summary_report["summary"]["total_cases"] == 6
    assert summary_report["summary"]["run_cases"] >= 3
    
    # Check that error metrics exist for deflection
    defl_metrics = summary_report["global_metrics"]["deflection"]
    assert "mae" in defl_metrics
    assert "rmse" in defl_metrics


def test_diagnostic_detection_heuristics(temp_benchmark_dir: str) -> None:
    """Verify runner diagnostics identify unit mismatches and load inconsistencies."""
    db = BenchmarkDatabase(temp_benchmark_dir)
    cases = db.discover_cases()
    
    runner = BenchmarkRunner()
    
    # 1. Retrieve the actual deflection calculated by RoadX solver
    valid_case = next(c for c in cases if c.case_id == "case_valid_template")
    valid_res = runner.parity_runner.run_case(valid_case.parity_case)
    act_defl = valid_res.roadx_outputs["deflection"]
    
    # 2. Patch the unit mismatch case in-memory to have expected deflection = act_defl / 1000.0
    unit_mismatch_case = next(c for c in cases if c.case_id == "case_unit_mismatch")
    pc = unit_mismatch_case.parity_case
    patched_expected = dict(pc.expected_iitpave_outputs)
    patched_expected["deflection"] = act_defl / 1000.0
    if "deflection_mm" in patched_expected:
        patched_expected["deflection_mm"] = act_defl / 1000.0
    
    patched_pc = ParityCase(
        case_id=pc.case_id,
        layers=pc.layers,
        subgrade=pc.subgrade,
        loads=pc.loads,
        observation_points=pc.observation_points,
        expected_iitpave_outputs=patched_expected,
        tolerance_limits=pc.tolerance_limits,
        source_file=pc.source_file,
        notes=pc.notes
    )
    
    patched_case = BenchmarkCase(
        case_id=unit_mismatch_case.case_id,
        is_official=unit_mismatch_case.is_official,
        json_path=unit_mismatch_case.json_path,
        out_path=unit_mismatch_case.out_path,
        parity_case=patched_pc,
        parse_status=unit_mismatch_case.parse_status,
        error_message=unit_mismatch_case.error_message
    )
    
    # 3. Run the patched case
    result = runner.run_case(patched_case)
    assert any("unit mismatch" in d.lower() for d in result["diagnostics"])
    
    # 4. Load radius mismatch / consistency check
    radius_case = next(c for c in cases if c.case_id == "case_radius_mismatch")
    radius_rec = runner.run_case(radius_case)
    assert any("wheel load" in d.lower() for d in radius_rec["diagnostics"])


def test_calibration_report_generation(temp_benchmark_dir: str) -> None:
    """Verify report generation formats Markdown, JSON, and CSV files successfully."""
    db = BenchmarkDatabase(temp_benchmark_dir)
    cases = db.discover_cases()
    
    runner = BenchmarkRunner()
    results = runner.run_batch(cases)
    
    stats_agg = BenchmarkStatistics()
    summary_report = stats_agg.aggregate(results)
    
    generator = CalibrationReportGenerator()
    with tempfile.TemporaryDirectory() as out_dir:
        md_path, json_path, csv_path = generator.save_reports(results, summary_report, out_dir)
        
        assert os.path.exists(md_path)
        assert os.path.exists(json_path)
        assert os.path.exists(csv_path)
        
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
            assert "# RoadX Multilayer Solver Calibration & Validation Report" in md_text
            assert "Maturity" in md_text
            
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
            assert "statistics" in json_data
            assert "cases" in json_data
            
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_lines = f.readlines()
            assert len(csv_lines) > 1
            assert "Case_ID" in csv_lines[0]


def test_solver_maturity_remains_experimental() -> None:
    """Verify that overall solver maturity is experimental and is not promoted without official datasets passing."""
    generator = CalibrationReportGenerator()
    
    stats = {
        "summary": {"total_cases": 1, "run_cases": 1, "passed_cases": 1, "failed_cases": 0, "pass_percentage": 100.0},
        "global_metrics": {k: {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "max_error": 0.0, "pct_95_error": 0.0} for k in ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]}
    }
    
    run_records = [{
        "case_id": "case_template_1",
        "is_official": False,
        "status": "template_case_pass",
        "parity_result": None
    }]
    
    md = generator.generate_markdown(run_records, stats)
    assert "**Overall Solver Maturity:** `EXPERIMENTAL`" in md
