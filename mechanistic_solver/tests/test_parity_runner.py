"""Unit tests for the validation parity runner."""
from __future__ import annotations

import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.validation.parity_models import ParityCase
from mechanistic_solver.validation.parity_runner import ParityRunner


def test_parity_runner_execution() -> None:
    """Verify that ParityRunner runs RoadX solver and computes errors successfully."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    
    # We place observation points at:
    # 1. Bottom of bituminous (z = 100.0 mm)
    # 2. Top of subgrade (z = 100.0 mm)
    points = [
        ObservationPoint(x=0.0, y=0.0, z=100.0)
    ]
    
    # Create expected outputs matching expected keys
    expected_outputs = {
        "tensile_strain_microstrain": 150.0,
        "vertical_strain_microstrain": 200.0,
        "vertical_stress_mpa": 0.4,
        "deflection_mm": 0.8
    }
    
    case = ParityCase(
        case_id="test_case_1",
        layers=(l1,),
        subgrade=sub,
        loads=(load,),
        observation_points=points,
        expected_iitpave_outputs=expected_outputs,
        notes="Synthetic test case"
    )
    
    # Verify runner executing case
    runner = ParityRunner()
    result = runner.run_case(case)
    
    assert result.case_id == "test_case_1"
    # roadx_outputs should be populated
    assert "epsilon_t_bottom_bituminous" in result.roadx_outputs
    assert result.roadx_outputs["epsilon_t_bottom_bituminous"] is not None
    assert result.roadx_outputs["epsilon_t_bottom_bituminous"] > 0.0
    
    assert "epsilon_v_top_subgrade" in result.roadx_outputs
    assert result.roadx_outputs["epsilon_v_top_subgrade"] is not None
    
    assert result.expected_outputs["epsilon_t_bottom_bituminous"] == 150.0
    assert result.expected_outputs["epsilon_v_top_subgrade"] == 200.0
    
    # Error computations should exist
    assert "epsilon_t_bottom_bituminous" in result.absolute_errors
    assert "epsilon_t_bottom_bituminous" in result.relative_errors
    assert "epsilon_t_bottom_bituminous" in result.pass_status


def test_parity_runner_run_all_summary() -> None:
    """Verify runner aggregates multiple results into a ParitySummary record."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    points = [ObservationPoint(0.0, 0.0, 100.0)]
    
    case = ParityCase(
        case_id="case_summary_1",
        layers=(l1,),
        subgrade=sub,
        loads=(load,),
        observation_points=points,
        expected_iitpave_outputs={
            "tensile_strain_microstrain": 200.0
        }
    )
    
    runner = ParityRunner()
    summary = runner.run_all([case])
    
    assert summary.total_cases == 1
    assert len(summary.case_results) == 1
    assert "epsilon_t_bottom_bituminous_mae" in summary.metrics
    assert summary.overall_status in ["validated_case_pass", "validated_case_fail", "experimental"]
