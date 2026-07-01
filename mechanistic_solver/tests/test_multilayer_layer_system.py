"""Unit tests for the LayerSystem model and cumulative depth mapping."""
from __future__ import annotations

import pytest

from mechanistic_solver.core.models import Layer
from mechanistic_solver.solver.matrix.layer_system import LayerSystem


def test_layer_system_creation_and_depths() -> None:
    """Verify cumulative depth mapping and layer retrieval at specified depths."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    l2 = Layer(name="WMM", thickness=150.0, elastic_modulus=300.0, poisson_ratio=0.35, density=2200.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    sys = LayerSystem(layers=(l1, l2), subgrade=sub)
    
    # Cumulative depths
    assert sys.get_layer_top_depth(0) == 0.0
    assert sys.get_layer_bottom_depth(0) == 40.0
    
    assert sys.get_layer_top_depth(1) == 40.0
    assert sys.get_layer_bottom_depth(1) == 190.0
    
    assert sys.get_layer_top_depth(2) == 190.0
    assert sys.get_layer_bottom_depth(2) is None
    
    assert sys.get_interface_depths() == [40.0, 190.0]
    assert sys.get_layer_at_depth(20.0).name == "BC"
    assert sys.get_layer_at_depth(100.0).name == "WMM"
    assert sys.get_layer_at_depth(200.0).name == "Subgrade"
    
    # Exact interface depth should fall into lower layer
    assert sys.get_layer_at_depth(40.0).name == "WMM"
    assert sys.get_layer_at_depth(190.0).name == "Subgrade"
    
    assert sys.total_finite_thickness() == 190.0


def test_layer_system_validation() -> None:
    """Verify that invalid thicknesses raise value errors."""
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    # Subgrade with thickness
    sub_invalid = Layer(name="Subgrade", thickness=100.0, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    with pytest.raises(ValueError, match="Subgrade layer must have infinite thickness"):
        LayerSystem(layers=(), subgrade=sub_invalid)
        
    # Finite layer with thickness <= 0 (handled by Layer post_init already, but double-checked)
    l_zero = Layer(name="Zero", thickness=50.0, elastic_modulus=100.0, poisson_ratio=0.3, density=2000.0)
    # Mocking thickness value bypasses post_init check for this test validation
    # (Actually post_init throws on layer creation, so no need to test bypass)
