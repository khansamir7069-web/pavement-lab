"""Unit tests for multilayer response evaluation and sanity checks."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_multilayer_response_sanity_cases() -> None:
    """Load multilayer_response_sanity_cases.json and evaluate real stress/strain/displacement values."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "multilayer_response_sanity_cases.json"
    assert fixture_path.exists()
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    solver = MechanisticSolver(mode="multilayer")
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    
    for case in cases:
        inputs = case["inputs"]
        expected = case["expected_outputs"]
        
        layers = [Layer.from_dict(l) for l in inputs["layers"]]
        sub = Layer.from_dict(inputs["subgrade"])
        pavement = Pavement(layers=layers, subgrade=sub)
        
        points = [ObservationPoint(p["x"], p["y"], p["z"]) for p in inputs["observation_points"]]
        
        response = solver.solve(pavement, [load], points)
        
        # Check overall solver status
        assert response.status == expected["status"]
        
        # Verify vertical stress is non-None and is a valid finite float
        stress = response.stress_results[0]
        assert stress["sigma_z"] is not None
        assert stress["sigma_z"] > 0.0  # Compressive vertical stress orient positive
        
        # Verify strain is computed
        strain = response.strain_results[0]
        assert strain["epsilon_z"] is not None
        
        # Verify vertical deflection is computed
        disp = response.displacement_results[0]
        assert disp["vertical_deflection"] is not None
        assert disp["vertical_deflection"] > 0.0
