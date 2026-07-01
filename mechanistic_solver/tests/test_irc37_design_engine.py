"""Unit tests for the IRC:37 mechanistic design engine."""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.core.models import Layer, Pavement, WheelLoad
from mechanistic_solver.design import (
    compute_fatigue_life,
    check_fatigue_adequacy,
    compute_rutting_life,
    check_rutting_adequacy,
    check_structural_adequacy,
    optimize_bituminous_thickness,
    RecommendationEngine,
    IRCDesignReportGenerator,
    IRC37DesignEngine,
)


def test_fatigue_equation_calculation() -> None:
    """Verify standard and boundary conditions of fatigue calculation model."""
    # Test valid calculations: eps_t = 120 microstrain (1.2e-4), E_BC = 3000 MPa
    n_f = compute_fatigue_life(1.2e-4, 3000.0)
    # n_f = 1.0 * 2.21e-4 * (1/1.2e-4)^3.89 * (1/3000)^0.854
    assert n_f > 0.0
    assert math.isfinite(n_f)
    
    # Tension strain <= 0 should yield infinite life
    assert compute_fatigue_life(-1.0e-5, 3000.0) == float("inf")
    assert compute_fatigue_life(0.0, 3000.0) == float("inf")
    
    with pytest.raises(ValueError, match="modulus must be positive"):
        compute_fatigue_life(1.0e-4, -100.0)


def test_rutting_equation_calculation() -> None:
    """Verify standard and boundary conditions of subgrade rutting model."""
    # Test valid calculations: eps_v = 220 microstrain (2.2e-4)
    n_r = compute_rutting_life(2.2e-4)
    # n_r = 4.1656e-8 * (1/2.2e-4)^4.5337
    assert n_r > 0.0
    assert math.isfinite(n_r)
    
    # Tension / negative vertical strain should yield infinite life
    assert compute_rutting_life(-1.0e-5) == float("inf")
    assert compute_rutting_life(0.0) == float("inf")


def test_traffic_msa_conversion() -> None:
    """Verify that MSA conversion is correct."""
    # 10 MSA = 10 * 1e6 = 10,000,000 standard axle repetitions
    fatigue_check = check_fatigue_adequacy(1.2e-4, 3000.0, 10.0)
    assert fatigue_check["design_traffic_msa"] == 10.0
    assert fatigue_check["allowable_repetitions_msa"] == fatigue_check["allowable_repetitions"] / 1.0e6
    
    with pytest.raises(ValueError, match="must be non-negative"):
        check_fatigue_adequacy(1.2e-4, 3000.0, -5.0)


def test_structural_adequacy_pass_fail() -> None:
    """Verify adequacy checks correctly combine fatigue/rutting and identify governing mode."""
    # Case 1: Both pass
    res_pass = check_structural_adequacy(
        epsilon_t=1.0e-6,  # extremely small strain -> passes
        e_bc_mpa=3000.0,
        epsilon_v=1.0e-6,
        design_traffic_msa=10.0
    )
    assert res_pass["overall_passed"] is True
    
    # Case 2: Fatigue fails, rutting passes
    res_fatigue_fail = check_structural_adequacy(
        epsilon_t=1.0e-2,  # extremely large strain -> fails
        e_bc_mpa=3000.0,
        epsilon_v=1.0e-6,
        design_traffic_msa=10.0
    )
    assert res_fatigue_fail["overall_passed"] is False
    assert res_fatigue_fail["governing_failure_mode"] == "fatigue"
    
    # Case 3: Rutting fails, fatigue passes
    res_rutting_fail = check_structural_adequacy(
        epsilon_t=1.0e-6,
        e_bc_mpa=3000.0,
        epsilon_v=1.0e-2,
        design_traffic_msa=10.0
    )
    assert res_rutting_fail["overall_passed"] is False
    assert res_rutting_fail["governing_failure_mode"] == "rutting"


def test_optimization_loop_and_minimum_thickness() -> None:
    """Verify optimization converges, does not violate bounds, and logs history."""
    l1 = Layer(name="Top", thickness=150.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    # Run optimization under 10 MSA
    opt_res = optimize_bituminous_thickness(
        pavement, (load,), design_traffic_msa=10.0,
        min_thickness_mm=50.0, max_thickness_mm=250.0, step_mm=10.0
    )
    
    assert opt_res["optimal_thickness_mm"] >= 50.0
    assert opt_res["optimal_thickness_mm"] <= 250.0
    assert len(opt_res["history"]) > 0
    
    # Verify that the first layer thickness in the optimized pavement matches the optimal thickness
    opt_pavement = opt_res["optimized_pavement"]
    assert opt_pavement.layers[0].thickness == opt_res["optimal_thickness_mm"]


def test_recommendation_triggers() -> None:
    """Verify recommendation rules generate correct explanations."""
    engine = RecommendationEngine()
    
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    # Case 1: Fatigue fails
    adeq_fatigue = {
        "fatigue_status": {"passed": False, "utilization_ratio": 2.5},
        "rutting_status": {"passed": True, "utilization_ratio": 0.3},
        "governing_failure_mode": "fatigue",
        "overall_passed": False
    }
    recs_fatigue = engine.generate_recommendations(pavement, adeq_fatigue, solver_status="experimental")
    assert any("Fatigue cracking governs" in r for r in recs_fatigue)
    
    # Case 2: Unrealistic stiffness ratio (subgrade stiffer than layer above it)
    sub_stiff = Layer(name="Subgrade", thickness=None, elastic_modulus=4000.0, poisson_ratio=0.4, density=1800.0)
    pavement_unrealistic = Pavement(layers=(l1,), subgrade=sub_stiff)
    adeq_pass = {
        "fatigue_status": {"passed": True, "utilization_ratio": 0.1},
        "rutting_status": {"passed": True, "utilization_ratio": 0.1},
        "governing_failure_mode": "none",
        "overall_passed": True
    }
    recs_stiff = engine.generate_recommendations(pavement_unrealistic, adeq_pass)
    assert any("Unrealistic stiffness ratio" in r for r in recs_stiff)
    
    # Case 3: Experimental solver warning
    assert any("Maturity Warning" in r for r in recs_fatigue)


def test_design_report_generation() -> None:
    """Verify Markdown and JSON design reports are generated correctly."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    engine = IRC37DesignEngine()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = engine.design_and_optimize(
            pavement, (load,), traffic_msa=5.0, output_dir=tmp_dir, min_thickness_mm=50.0, step_mm=10.0
        )
        
        md_path = Path(res["report_paths"]["markdown"])
        json_path = Path(res["report_paths"]["json"])
        
        assert md_path.exists()
        assert json_path.exists()
        
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
            assert "# RoadX Mechanistic Pavement Design Report" in md_text
            assert "Design Traffic" in md_text
            
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
            assert "pavement" in json_data
            assert "adequacy" in json_data
            assert "optimization" in json_data
            assert "recommendations" in json_data
            # Verify solver maturity is experimental in the report
            assert json_data["solver_status"] == "experimental"
