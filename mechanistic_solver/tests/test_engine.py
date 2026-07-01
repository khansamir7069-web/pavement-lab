"""Unit tests for the mechanistic solver engine interface and response values."""
from __future__ import annotations

import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_solver_engine_interface() -> None:
    """Verify that the solver interface validates inputs and returns a Response structure."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point = ObservationPoint(x=0.0, y=0.0, z=100.0)
    
    solver = MechanisticSolver(mode="halfspace")
    response = solver.solve(
        pavement=pavement,
        loads=[load],
        observation_points=[point]
    )
    
    # Assert return types and structures
    assert response.surface_deflection > 0.0
    assert response.runtime_seconds >= 0.0
    assert response.metadata["solver_state"] == "halfspace_computed"
    assert response.metadata["observation_points_count"] == 1
    assert response.metadata["wheel_loads_count"] == 1
    assert response.solver_version == "1.0.0"
    
    assert len(response.stress_results) == 1
    assert len(response.strain_results) == 1


def test_solver_engine_validation() -> None:
    """Verify that solver solves reject empty parameters lists."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point = ObservationPoint(x=0.0, y=0.0, z=100.0)
    
    solver = MechanisticSolver(mode="halfspace")
    
    # Empty loads
    with pytest.raises(ValueError, match="At least one wheel load configuration is required"):
        solver.solve(pavement, [], [point])
        
    # Empty points
    with pytest.raises(ValueError, match="At least one evaluation observation point is required"):
        solver.solve(pavement, [load], [])
