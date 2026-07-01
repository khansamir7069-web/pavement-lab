"""Multilayer strain evaluator using Hooke's Law.

Converts calculated stress tensors to strain components.
"""
from __future__ import annotations

from typing import Any, Mapping
from mechanistic_solver.core.models import Layer


def evaluate_strain(
    stress_result: Mapping[str, Any],
    layer: Layer
) -> dict[str, Any]:
    """Convert stress results to strain components using isotropic Hooke's law."""
    sigma_z = stress_result.get("sigma_z")
    sigma_r = stress_result.get("sigma_r")
    sigma_theta = stress_result.get("sigma_theta")
    tau_rz = stress_result.get("tau_rz")
    
    warnings = list(stress_result.get("warnings", []))
    
    if sigma_z is None or sigma_r is None or sigma_theta is None:
        return {
            "epsilon_z": None,
            "epsilon_r": None,
            "epsilon_t": None,
            "gamma_zr": None,
            "status": "partial",
            "method": "isotropic_hookes_law_multilayer",
            "warnings": warnings + ["Strains cannot be computed because stresses are incomplete (None)."]
        }
        
    E = float(layer.elastic_modulus)  # MPa
    nu = float(layer.poisson_ratio)
    
    s_z = float(sigma_z)
    s_r = float(sigma_r)
    s_t = float(sigma_theta)
    t_rz = float(tau_rz) if tau_rz is not None else 0.0
    
    # Strains (dimensionless, microstrain in future checks)
    epsilon_z = (s_z - nu * (s_r + s_t)) / E
    epsilon_r = (s_r - nu * (s_z + s_t)) / E
    epsilon_t = (s_t - nu * (s_z + s_r)) / E
    gamma_zr = (2.0 * (1.0 + nu) * t_rz) / E
    
    return {
        "epsilon_z": epsilon_z,
        "epsilon_r": epsilon_r,
        "epsilon_t": epsilon_t,
        "gamma_zr": gamma_zr,
        "status": "experimental",
        "method": "isotropic_hookes_law_multilayer",
        "warnings": warnings
    }
