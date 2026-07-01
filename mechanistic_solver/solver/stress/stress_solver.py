"""Axisymmetric layered elastic stress tensor solver.

Implements Boussinesq point-load equations and circular load centerline stress
dispatches using SI units.
"""
from __future__ import annotations

import math
from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.kernels.boussinesq import (
    radial_stress_point_load,
    shear_stress_point_load,
    tangential_stress_point_load,
    vertical_stress_circular_axis,
    vertical_stress_point_load,
)


def compute_halfspace_stress(
    load: WheelLoad,
    point: ObservationPoint,
    elastic_modulus: float,  # in MPa
    poisson_ratio: float
) -> dict[str, Any]:
    """Compute stress tensor for single-layer half-space using Boussinesq.

    Returns:
        dict: containing vertical_stress (sigma_z), radial_stress (sigma_r),
              tangential_stress (sigma_theta), shear_stress (tau_rz), method, and units.
    """
    # Convert values to SI units
    P = float(load.wheel_load) * 1000.0          # kN -> N
    q = float(load.pressure) * 1000000.0         # MPa -> Pa
    a = float(load.radius) / 1000.0              # mm -> m
    
    # Coordinates in meters
    x_load = float(load.x) / 1000.0
    y_load = float(load.y) / 1000.0
    x_pt = float(point.x) / 1000.0
    y_pt = float(point.y) / 1000.0
    z = float(point.z) / 1000.0
    
    dx = x_pt - x_load
    dy = y_pt - y_load
    r = math.sqrt(dx * dx + dy * dy)
    
    method = "boussinesq_point_load"
    
    if r < 1e-10:
        # Centerline of circular load
        method = "boussinesq_circular_axis"
        sigma_z = vertical_stress_circular_axis(q, a, z)
        
        # Centerline radial and tangential stresses
        # sigma_r = sigma_theta = q/2 * [ (1+2*nu) - 2*(1+nu)*z/sqrt(a^2+z^2) + z^3/(a^2+z^2)^1.5 ]
        denom = math.sqrt(a * a + z * z)
        term1 = 1.0 + 2.0 * poisson_ratio
        term2 = (2.0 * (1.0 + poisson_ratio) * z) / denom
        term3 = (z ** 3) / (denom ** 3)
        sigma_r = (q / 2.0) * (term1 - term2 + term3)
        sigma_theta = sigma_r
        tau_rz = 0.0
    else:
        # Off-axis point load approximation
        sigma_z = vertical_stress_point_load(P, r, z)
        sigma_r = radial_stress_point_load(P, r, z, poisson_ratio)
        sigma_theta = tangential_stress_point_load(P, r, z, poisson_ratio)
        tau_rz = shear_stress_point_load(P, r, z)
        
    return {
        "sigma_z": sigma_z,
        "sigma_r": sigma_r,
        "sigma_theta": sigma_theta,
        "tau_rz": tau_rz,
        "method": method,
        "units": "Pa",
    }
