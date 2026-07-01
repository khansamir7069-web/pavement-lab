"""Multilayer displacement calculation dispatch layer.

Routes vertical deflection calculations to evaluate_displacement.
"""
from __future__ import annotations

from typing import Any

from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.evaluation.displacement_evaluator import evaluate_displacement


def compute_multilayer_displacement(
    layer_system: LayerSystem,
    load: WheelLoad,
    point: ObservationPoint,
    boundary_conditions: BoundaryConditionSet
) -> dict[str, Any]:
    """Calculate displacement for multilayer structures using Hankel integration."""
    return evaluate_displacement(
        layer_system=layer_system,
        coefficients=None,
        load=load,
        point=point,
        boundary_conditions=boundary_conditions
    )
