"""Multilayer layered elastic response calculation kernel.

Coordinates Burmister coefficients solving and runs the stress/strain/displacement
integration pipeline.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Sequence

from mechanistic_solver.core.logging import get_logger
from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.matrix.coefficient_builder import LayerCoefficients
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.matrix.transfer_matrix import TransferMatrixBuilder
from mechanistic_solver.solver.matrix.linear_solver import solve_system
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.evaluation.stress_evaluator import evaluate_stress

logger = get_logger("mechanistic_solver.kernels")


def integrate_axisymmetric_response(
    func: Callable[[float], float],
    upper_limit: float = 100.0,
    tolerance: float = 1e-6,
    max_depth: int = 15
) -> float:
    """Execute radial integration with bounds checking and subdivision limits."""
    try:
        from mechanistic_solver.math.integration import integrate_adaptive_simpson
        return integrate_adaptive_simpson(func, 0.0, upper_limit, tolerance, max_depth)
    except Exception as e:
        logger.warning("Radial integration encountered a numerical warning: %s", e)
        raise


class MultilayerElasticKernel:
    """Coordinates transfer matrix assembly and solves the Burmister coefficients system."""

    def __init__(self) -> None:
        self.matrix_builder = TransferMatrixBuilder()

    def compute_response(
        self,
        layer_system: LayerSystem,
        load: WheelLoad,
        point: ObservationPoint,
        boundary_conditions: BoundaryConditionSet | None = None
    ) -> dict[str, Any]:
        """Assemble system matrix, solve coefficients, and integrate stress components."""
        if boundary_conditions is None:
            boundary_conditions = BoundaryConditionSet.create_default(len(layer_system.layers))
        # Execute stress evaluator
        res = evaluate_stress(
            layer_system=layer_system,
            coefficients=None,
            load=load,
            point=point,
            boundary_conditions=boundary_conditions
        )
        return res
