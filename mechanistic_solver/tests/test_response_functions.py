"""Unit tests for the response functions builder in the radial-parameter domain."""
from __future__ import annotations

from mechanistic_solver.core.models import Layer, WheelLoad
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.evaluation.response_functions import (
    build_sigma_z_function,
    build_vertical_displacement_function,
)


def test_response_functions_construction() -> None:
    """Verify that vertical stress and displacement response functions construct correctly."""
    l1 = Layer(name="BC", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    sys = LayerSystem(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    
    # Radius in meters, pressure in Pa
    a_m = 0.15
    q_pa = 560000.0
    
    func_z = build_sigma_z_function(sys, a_m, q_pa, z_m=0.05)
    func_w = build_vertical_displacement_function(sys, a_m, q_pa, z_m=0.05)
    
    # Evaluate at a test parameter m = 1.5
    val_z = func_z(1.5)
    val_w = func_w(1.5)
    
    assert isinstance(val_z, float)
    assert isinstance(val_w, float)
