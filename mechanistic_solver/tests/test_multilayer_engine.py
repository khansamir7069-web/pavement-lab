"""Unit tests for the solver engine under multilayer mode."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from mechanistic_solver.core.exceptions import InvalidLayerConfigurationError
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_multilayer_engine_mode() -> None:
    """Verify that mode='multilayer' returns Response with partial results and warnings."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point = ObservationPoint(x=0.0, y=0.0, z=20.0)
    
    solver = MechanisticSolver(mode="multilayer")
    response = solver.solve(pavement, [load], [point])
    
    # Verify response schema fields
    assert response.status == "experimental"
    assert response.surface_deflection > 0.0
    assert response.stress_results[0]["sigma_z"] is not None
    assert response.stress_results[0]["layer_name"] == "BC"
    assert response.stress_results[0]["layer_index"] == 0
    assert response.strain_results[0]["epsilon_z"] is not None
    assert response.displacement_results[0]["vertical_deflection"] is not None


def test_golden_multilayer_sanity_cases() -> None:
    """Load golden_multilayer_sanity_cases.json and verify all cases through the engine."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "golden_multilayer_sanity_cases.json"
    assert fixture_path.exists()
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    solver = MechanisticSolver(mode="multilayer")
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    
    for case in cases:
        inputs = case["inputs"]
        expected = case["expected_outputs"]
        
        # Load layers
        layers = [Layer.from_dict(l) for l in inputs["layers"]]
        sub = Layer.from_dict(inputs["subgrade"])
        pavement = Pavement(layers=layers, subgrade=sub)
        
        points = [ObservationPoint(p["x"], p["y"], p["z"]) for p in inputs["observation_points"]]
        
        response = solver.solve(pavement, [load], points)
        
        # Check target layer identification
        res_stress = response.stress_results[0]
        assert res_stress["layer_name"] == expected["layer_name"]
        if "layer_index" in expected:
            assert res_stress["layer_index"] == expected["layer_index"]
            
        assert response.status == "experimental"
        assert res_stress["sigma_z"] is not None


def test_unsupported_multilayer_configuration() -> None:
    """Verify that Pavement raises exception if zero finite layers are present."""
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    with pytest.raises(InvalidLayerConfigurationError, match="must contain at least one finite layer"):
        Pavement(layers=(), subgrade=sub)
