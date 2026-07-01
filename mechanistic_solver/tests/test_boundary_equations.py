"""Unit tests for Burmister boundary equations matrix assembly."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from mechanistic_solver.core.models import Layer
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.matrix.boundary_equations import assemble_bonded_system


def test_boundary_equations_assembly_and_dimensions() -> None:
    """Load reference cases and verify equation matrix shapes match 4n-2 exactly."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "bonded_boundary_reference_cases.json"
    assert fixture_path.exists()
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    for case in cases:
        inputs = case["inputs"]
        expected_dim = case["expected_matrix_dim"]
        
        layers = [Layer.from_dict(l) for l in inputs["layers"]]
        sub = Layer.from_dict(inputs["subgrade"])
        sys = LayerSystem(layers=layers, subgrade=sub)
        
        A, B = assemble_bonded_system(
            layer_system=sys,
            radial_parameter=1.0,
            wheel_load_radius_m=0.15,
            contact_pressure_pa=560000.0
        )
        
        # Verify matrix shape is exactly (4n-2, 4n-2)
        assert A.shape == (expected_dim, expected_dim)
        assert len(B) == expected_dim
        
        # Check boundary vector surface load term is populated
        assert B[0] > 0.0
        assert B[1] == 0.0
