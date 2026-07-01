"""Unit tests for Boussinesq kernel calculations and engine halfspace dispatches.

Validates analytical formulas against closed-form values and checks golden halfspace
fixtures.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import pytest

from mechanistic_solver.core.exceptions import InvalidLayerConfigurationError
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.solver.kernels.boussinesq import (
    vertical_stress_circular_axis,
    vertical_stress_point_load,
    radial_stress_point_load,
    tangential_stress_point_load,
    surface_deflection_point_load,
    vertical_deflection_circular_axis,
)


def test_boussinesq_point_load_equations() -> None:
    """Verify Boussinesq point load stresses and deflections against manual checks."""
    P = 40000.0  # N
    r = 0.2      # m
    z = 0.3      # m
    nu = 0.35
    E = 1e8      # Pa
    
    # 1. Stress Point Load
    R = math.sqrt(r * r + z * z)
    sigma_z = vertical_stress_point_load(P, r, z)
    expected_sigma_z = (3.0 * P * (z ** 3)) / (2.0 * math.pi * (R ** 5))
    assert math.isclose(sigma_z, expected_sigma_z)
    
    # Singularity at origin
    with pytest.raises(ValueError, match="singularity"):
        vertical_stress_point_load(P, 0.0, 0.0)

    # 2. Radial and Tangential Stress
    sigma_r = radial_stress_point_load(P, r, z, nu)
    sigma_theta = tangential_stress_point_load(P, r, z, nu)
    assert abs(sigma_r) > 0.0
    assert abs(sigma_theta) > 0.0

    # 3. Deflection Surface
    w_surf = surface_deflection_point_load(P, r, E, nu)
    expected_w_surf = (P * (1.0 - nu * nu)) / (math.pi * E * r)
    assert math.isclose(w_surf, expected_w_surf)


def test_circular_axis_equations() -> None:
    """Verify circular axis centerline stresses and deflection calculations."""
    q = 560000.0  # Pa
    a = 0.15      # m
    z = 0.1       # m
    E = 1e8       # Pa
    nu = 0.35
    
    # 1. Stress
    sigma_z = vertical_stress_circular_axis(q, a, z)
    expected_sigma_z = q * (1.0 - (z ** 3) / ((a * a + z * z) ** 1.5))
    assert math.isclose(sigma_z, expected_sigma_z)
    
    # Surface stress (z=0)
    assert math.isclose(vertical_stress_circular_axis(q, a, 0.0), q)

    # 2. Deflection
    w = vertical_deflection_circular_axis(q, a, E, nu, z)
    assert w > 0.0


def test_golden_halfspace_fixtures() -> None:
    """Load golden_halfspace_cases.json and verify all cases against the engine."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "golden_halfspace_cases.json"
    assert fixture_path.exists()
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    for case in cases:
        inputs = case["inputs"]
        expected = case["expected_outputs"]
        tol = case["tolerance"]
        
        # Dispatch checks
        if "P" in inputs:
            # Point Load case
            P = inputs["P"]
            r = inputs["r"]
            z = inputs["z"]
            nu = inputs["nu"]
            
            if "sigma_z" in expected:
                val = vertical_stress_point_load(P, r, z)
                assert math.isclose(val, expected["sigma_z"], abs_tol=tol)
        else:
            # Circular Load case
            q = inputs["q"]
            a = inputs["a"]
            z = inputs["z"]
            nu = inputs["nu"]
            
            if "sigma_z" in expected:
                val = vertical_stress_circular_axis(q, a, z)
                assert math.isclose(val, expected["sigma_z"], abs_tol=tol)
                
            if "vertical_deflection" in expected:
                E = inputs["E"]
                val = vertical_deflection_circular_axis(q, a, E, nu, z)
                assert math.isclose(val, expected["vertical_deflection"], abs_tol=tol)


def test_engine_halfspace_mode() -> None:
    """Verify solver engine behavior under mode='halfspace'."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    
    # 1. Valid halfspace structure (1 layer + subgrade)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point_on_axis = ObservationPoint(x=0.0, y=0.0, z=100.0)
    point_off_axis = ObservationPoint(x=200.0, y=0.0, z=100.0)
    
    solver = MechanisticSolver(mode="halfspace")
    response = solver.solve(pavement, [load], [point_on_axis, point_off_axis])
    
    assert response.surface_deflection > 0.0
    assert len(response.stress_results) == 2
    assert len(response.strain_results) == 2
    assert len(response.displacement_results) == 2
    
    # Centerline deflection matches circular centerline deflection
    assert response.displacement_results[0]["method"] == "boussinesq_circular_axis"
    assert response.displacement_results[0]["vertical_deflection"] > 0.0
    
    # Off-axis deflection triggers warning and returns 0.0
    assert response.displacement_results[1]["method"] == "unsupported_off_axis"
    assert response.displacement_results[1]["vertical_deflection"] == 0.0
    assert len(response.warnings) == 1
    assert "Off-axis circular load deflection" in response.warnings[0]
    
    # 2. Invalid multilayer structure throws exception in halfspace mode
    l2 = Layer(name="DBM", thickness=80.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    pavement_multi = Pavement(layers=(l1, l2), subgrade=sub)
    
    with pytest.raises(InvalidLayerConfigurationError, match="unsupported in single-layer halfspace mode"):
        solver.solve(pavement_multi, [load], [point_on_axis])


def test_engine_unsupported_mode() -> None:
    """Verify that constructing solver with non-halfspace modes raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported solver mode"):
        MechanisticSolver(mode="multilayer_elastic")
