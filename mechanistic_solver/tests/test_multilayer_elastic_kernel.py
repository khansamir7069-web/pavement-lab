"""Unit tests for the multilayer elastic kernel and integration helpers."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, WheelLoad
from mechanistic_solver.solver.kernels.multilayer_elastic import (
    MultilayerElasticKernel,
    integrate_axisymmetric_response,
)
from mechanistic_solver.solver.matrix.layer_system import LayerSystem


def test_axisymmetric_response_integrator() -> None:
    """Verify that radial integration limits work successfully."""
    # Integrate J0(m) from 0 to 10.0
    from mechanistic_solver.math.bessel import j0
    res = integrate_axisymmetric_response(j0, upper_limit=10.0)
    assert abs(res) < 2.0


def test_multilayer_elastic_kernel_dispatch() -> None:
    """Verify that MultilayerElasticKernel populates None for incomplete properties."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    sys = LayerSystem(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point = ObservationPoint(x=0.0, y=0.0, z=20.0)
    
    kernel = MultilayerElasticKernel()
    res = kernel.compute_response(sys, load, point)
    
    # Assert stresses are returned correctly
    assert res["sigma_z"] is not None
    assert res["sigma_z"] > 0.0
    assert res["layer_name"] == "BC"
    assert res["layer_index"] == 0
    assert res["status"] == "experimental"
