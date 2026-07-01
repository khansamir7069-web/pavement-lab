"""Multilayer displacement evaluator using Hankel Integration.

Computes vertical deflection (deflection w) at Point (r, z) in meters.
"""
from __future__ import annotations

import math
from typing import Any

from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.integration.hankel_integrator import HankelIntegrator
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.evaluation.response_functions import build_vertical_displacement_function


def evaluate_displacement(
    layer_system: LayerSystem,
    coefficients: Any,  # Kept for backward compatibility interface
    load: WheelLoad,
    point: ObservationPoint,
    boundary_conditions: BoundaryConditionSet,
    integration_settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate vertical deflection at observation point (x, y, z) in meters."""
    r_m = math.sqrt(point.x * point.x + point.y * point.y) / 1000.0
    z_m = point.z / 1000.0
    
    a = float(load.radius) / 1000.0
    q = float(load.pressure) * 1e6
    
    integrator = HankelIntegrator()
    warnings: list[str] = []
    integration_reports: dict[str, Any] = {}
    
    try:
        func_w = build_vertical_displacement_function(layer_system, a, q, z_m)
        res_w = integrator.integrate_order0(func_w, r_m, kernel_length=a)
        vertical_deflection = res_w.value  # in meters
        integration_reports["vertical_deflection"] = res_w.to_dict()
        warnings.extend(res_w.warnings)
        status = "experimental"
    except Exception as e:
        vertical_deflection = None
        status = "failed"
        warnings.append(f"Vertical deflection integration failed: {e}")
        
    return {
        "vertical_deflection": vertical_deflection,
        "status": status,
        "method": "burmister_hankel_displacement",
        "units": "m",
        "integration_report": integration_reports,
        "warnings": list(set(warnings))
    }
