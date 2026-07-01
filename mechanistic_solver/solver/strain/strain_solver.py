"""Isotropic linear elastic strain tensor calculations.

Converts stress tensor components to strain components using Hooke's Law.
"""
from __future__ import annotations

from typing import Any, Mapping


def compute_halfspace_strain(
    stress_result: Mapping[str, Any],
    elastic_modulus: float,  # in MPa
    poisson_ratio: float
) -> dict[str, Any]:
    """Compute strain tensor from stress tensor using Hooke's Law.

    Args:
        stress_result: Stress dict containing sigma_z, sigma_r, sigma_theta, tau_rz in Pa.
        elastic_modulus: Modulus in MPa.
        poisson_ratio: Poisson's ratio.

    Returns:
        dict: containing epsilon_z, epsilon_r, epsilon_t, gamma_zr, method, and units.
    """
    # Convert modulus to Pascals
    E = float(elastic_modulus) * 1000000.0
    nu = float(poisson_ratio)
    
    sigma_z = float(stress_result["sigma_z"])
    sigma_r = float(stress_result["sigma_r"])
    sigma_theta = float(stress_result["sigma_theta"])
    tau_rz = float(stress_result.get("tau_rz", 0.0))
    
    # Hooke's Law
    epsilon_z = (sigma_z - nu * (sigma_r + sigma_theta)) / E
    epsilon_r = (sigma_r - nu * (sigma_theta + sigma_z)) / E
    epsilon_t = (sigma_theta - nu * (sigma_r + sigma_z)) / E
    
    # Shear strain gamma_rz = tau_rz / G = 2 * (1 + nu) / E * tau_rz
    gamma_zr = (2.0 * (1.0 + nu) * tau_rz) / E
    
    return {
        "epsilon_z": epsilon_z,
        "epsilon_r": epsilon_r,
        "epsilon_t": epsilon_t,
        "gamma_zr": gamma_zr,
        "method": "isotropic_hookes_law",
        "units": "dimensionless",
    }
