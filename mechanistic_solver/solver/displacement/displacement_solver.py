"""Layered elastic displacement solver.

Computes centerline vertical deflection under circular tire contact areas.
Off-axis points return structured warning/unsupported status.
"""
from __future__ import annotations

import math
from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.kernels.boussinesq import vertical_deflection_circular_axis


def compute_halfspace_deflection(
    load: WheelLoad,
    point: ObservationPoint,
    elastic_modulus: float,  # in MPa
    poisson_ratio: float
) -> dict[str, Any]:
    """Compute vertical deflection (w) for single-layer half-space centerline.

    Args:
        load: Tire contact load.
        point: Evaluation observation point coordinates.
        elastic_modulus: Modulus in MPa.
        poisson_ratio: Poisson's ratio.

    Returns:
        dict: containing vertical_deflection, method, units, and warning (if off-axis).
    """
    # Convert inputs to SI
    q = float(load.pressure) * 1000000.0         # MPa -> Pa
    a = float(load.radius) / 1000.0              # mm -> m
    E = float(elastic_modulus) * 1000000.0       # MPa -> Pa
    nu = float(poisson_ratio)
    
    # Coordinates in meters
    x_load = float(load.x) / 1000.0
    y_load = float(load.y) / 1000.0
    x_pt = float(point.x) / 1000.0
    y_pt = float(point.y) / 1000.0
    z = float(point.z) / 1000.0
    
    dx = x_pt - x_load
    dy = y_pt - y_load
    r = math.sqrt(dx * dx + dy * dy)
    
    if r < 1e-10:
        w = vertical_deflection_circular_axis(q, a, E, nu, z)
        return {
            "vertical_deflection": w,
            "method": "boussinesq_circular_axis",
            "units": "m",
            "warning": None,
        }
    else:
        return {
            "vertical_deflection": 0.0,
            "method": "unsupported_off_axis",
            "units": "m",
            "warning": "Off-axis circular load deflection is unsupported in single-layer half-space mode.",
        }
