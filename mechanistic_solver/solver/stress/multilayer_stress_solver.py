"""Multilayer stress calculation dispatch layer.

Coordinates coefficients solvers and Hankel integration.
"""
from __future__ import annotations

from typing import Any

from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.kernels.multilayer_elastic import MultilayerElasticKernel
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.matrix.layer_system import LayerSystem


def compute_multilayer_stress(
    layer_system: LayerSystem,
    load: WheelLoad,
    point: ObservationPoint,
    boundary_conditions: BoundaryConditionSet
) -> dict[str, Any]:
    """Calculate stress tensor for multilayer pavement structures.

    Returns:
        dict: containing stress values, method name, status, and warnings.
    """
    if len(boundary_conditions.interface_conditions) != len(layer_system.layers):
        raise ValueError("Interface conditions count must match the number of finite interfaces.")
        
    kernel = MultilayerElasticKernel()
    return kernel.compute_response(layer_system, load, point, boundary_conditions)
