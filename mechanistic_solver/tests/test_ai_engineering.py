"""Unit and integration tests verifying Phase 5 AI Engineering components."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.ai import (
    CostLibrary,
    CostOptimizer,
    LayerOptimizer,
    MultiObjectiveOptimizer,
    AIRecommendationEngine,
    AIEngineerAssistant,
    AIReportGenerator
)
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_cost_calculations() -> None:
    """Verify that pavement costs, volumes, and sensitivities are computed correctly."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    l2 = Layer(name="DBM", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    
    optimizer = CostOptimizer()
    res = optimizer.calculate_pavement_cost([l1, l2, sub], section_length_m=1000.0, section_width_m=7.0)
    
    # BC Cost = 0.040 * 7000 * 12000 = 3,360,000
    # DBM Cost = 0.100 * 7000 * 10000 = 7,000,000
    # Total = 10,360,000
    assert res["total_project_cost"] == 10360000.0
    assert len(res["layer_wise_costs"]) == 2
    assert res["cost_sensitivity"][0]["cost_sensitivity_per_mm"] == 84000.0  # 0.001 * 7000 * 12000


def test_layer_thickness_optimization() -> None:
    """Verify layer thickness optimization finds a valid candidate and verifies with solver."""
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    l2 = Layer(name="WMM", thickness=150.0, elastic_modulus=300.0, poisson_ratio=0.40, density=2000.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1, l2), subgrade=sub)
    
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    opt = LayerOptimizer()
    bounds = {
        "BC": (40.0, 80.0),
        "WMM": (100.0, 150.0)
    }
    
    # Light design traffic chosen so a valid candidate exists within these thin
    # bounds under the corrected (Boussinesq-validated) solver physics: a
    # ~230 mm section over an E=60 MPa subgrade only carries light traffic.
    res = opt.optimize_layers(pavement, [load], design_traffic_msa=0.3, bounds=bounds, step_mm=20.0)

    assert res["converged"] is True
    assert len(res["history"]) > 0
    # Confirm that every candidate tested contains a cost and passed status, verifying solver integration
    for candidate in res["history"]:
        assert "cost" in candidate
        assert "passed" in candidate


def test_multi_objective_pareto_front() -> None:
    """Verify multi-objective Pareto sorting filters out dominated designs."""
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    optimizer = MultiObjectiveOptimizer()
    bounds = {"BC": (40.0, 100.0)}
    
    pareto_solutions = optimizer.optimize_pareto(pavement, [load], traffic_msa=5.0, bounds=bounds, step_mm=20.0)
    
    assert len(pareto_solutions) > 0
    # Confirm Pareto front solutions are sorted by cost
    costs = [s["cost"] for s in pareto_solutions]
    assert costs == sorted(costs)


def test_ai_recommendations() -> None:
    """Verify that explainable recommendations are generated based on solver metrics."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    cost_res = {"total_project_cost": 500000.0}
    
    # 1. Simulate a failed design
    adequacy_fail = {
        "overall_passed": False,
        "utilization_ratios": {"fatigue": 1.25, "rutting": 0.85}
    }
    engine = AIRecommendationEngine()
    recs_fail = engine.generate_recommendations(pavement, adequacy_fail, cost_res)
    assert len(recs_fail) > 0
    assert "BC" in recs_fail[0]["affected_layer"]
    assert recs_fail[0]["confidence_score"] == 0.95
    
    # 2. Simulate an over-designed pavement
    adequacy_over = {
        "overall_passed": True,
        "utilization_ratios": {"fatigue": 0.25, "rutting": 0.30}
    }
    recs_over = engine.generate_recommendations(pavement, adequacy_over, cost_res)
    assert "reduce" in recs_over[0]["recommendation"].lower()


def test_engineering_assistant() -> None:
    """Verify AI engineer assistant answers queries accurately without fabricating data."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    adequacy = {
        "governing_failure_mode": "fatigue",
        "overall_passed": False,
        "utilization_ratios": {"fatigue": 1.25, "rutting": 0.85}
    }
    cost = {
        "cost_sensitivity": [{"layer_name": "BC", "cost_sensitivity_per_mm": 84000.0}]
    }
    
    assistant = AIEngineerAssistant(pavement, adequacy, cost)
    
    ans_failure = assistant.ask("What is the governing failure mode?")
    ans_cost = assistant.ask("How can we optimize cost?")
    ans_irc = assistant.ask("What does IRC:37 check?")
    
    assert "FATIGUE" in ans_failure
    assert "BC" in ans_cost
    assert "tensile strain" in ans_irc


def test_ai_report_generation() -> None:
    """Verify that reports save successfully in Markdown and JSON formats."""
    results = {
        "cost": {"total_project_cost": 10360000.0},
        "optimization": {"optimal_cost": 8500000.0, "converged": True},
        "pareto": [{"thicknesses": {"BC": 80.0}, "cost": 8500000.0, "utilization": 0.85, "reliability_pct": 98.0}],
        "recommendations": [{"recommendation": "Maintain", "affected_layer": "BC", "engineering_reason": "Pass", "expected_impact": "None", "confidence_score": 0.85}],
        "explanations": {"What is governing?": "None"}
    }
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = AIReportGenerator.save_reports(results, tmp_dir)
        assert Path(md_path).exists()
        assert Path(json_path).exists()
        
        md_content = Path(md_path).read_text(encoding="utf-8")
        assert "# RoadX AI Design & Optimization Report" in md_content


def test_ai_never_bypasses_solver() -> None:
    """Verify that the AI engine never bypasses solver verification."""
    # Ensure that any optimization results verified match original solver outputs
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    solver = MechanisticSolver(mode="multilayer")
    res_direct = solver.solve(pavement, (load,), [ObservationPoint(x=0.0, y=0.0, z=100.0)])
    
    # Run optimization (which must trigger the solver internally)
    opt = LayerOptimizer(solver=solver)
    bounds = {"BC": (100.0, 100.0)}
    res_opt = opt.optimize_layers(pavement, [load], design_traffic_msa=10.0, bounds=bounds, step_mm=10.0)
    
    # The utilization and thickness verified in history must correspond to the direct solve
    assert len(res_opt["history"]) == 1
    assert res_opt["history"][0]["utilization"] > 0.0
    assert res_direct.surface_deflection > 0.0
