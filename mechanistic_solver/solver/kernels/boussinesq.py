"""Boussinesq analytical elastic half-space response calculations.

Implements point load and circular load centerline stress and displacement
equations. Uses SI units: meters, Newtons, Pascals.
"""
from __future__ import annotations

import math
from mechanistic_solver.math.numerical import is_near_zero, validate_finite_number


def vertical_stress_point_load(P: float, r: float, z: float) -> float:
    """Compute vertical stress (sigma_z) under point load P.

    Equation: sigma_z = 3 * P * z^3 / (2 * pi * R^5)
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(z, "z")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
        
    R = math.sqrt(r * r + z * z)
    if is_near_zero(R):
        raise ValueError("Point-load stress singularity at exact load origin (R=0).")
        
    return (3.0 * P * (z ** 3)) / (2.0 * math.pi * (R ** 5))


def radial_stress_point_load(P: float, r: float, z: float, nu: float) -> float:
    """Compute radial stress (sigma_r) under point load P.

    Equation: sigma_r = P / (2 * pi * R^2) * (3 * r^2 * z / R^3 - (1 - 2*nu)/(1 + z/R))
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(z, "z")
    validate_finite_number(nu, "nu")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
    if nu <= 0.0 or nu >= 0.5:
        raise ValueError(f"Poisson's ratio nu must be in the range (0.0, 0.5). Got: {nu}.")
        
    R = math.sqrt(r * r + z * z)
    if is_near_zero(R):
        raise ValueError("Point-load stress singularity at exact load origin (R=0).")
        
    term1 = (3.0 * (r ** 2) * z) / (R ** 3)
    term2 = (1.0 - 2.0 * nu) / (1.0 + z / R)
    return (P / (2.0 * math.pi * (R ** 2))) * (term1 - term2)


def tangential_stress_point_load(P: float, r: float, z: float, nu: float) -> float:
    """Compute tangential stress (sigma_theta) under point load P.

    Equation: sigma_theta = P * (1 - 2*nu) / (2 * pi) * (-z / R^3 + 1 / (R * (R + z)))
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(z, "z")
    validate_finite_number(nu, "nu")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
    if nu <= 0.0 or nu >= 0.5:
        raise ValueError(f"Poisson's ratio nu must be in the range (0.0, 0.5). Got: {nu}.")
        
    R = math.sqrt(r * r + z * z)
    if is_near_zero(R):
        raise ValueError("Point-load stress singularity at exact load origin (R=0).")
        
    if is_near_zero(R + z):
        # Singularity at boundary point on vertical line z=-R (only possible if R=0, already checked, or z < 0, already validated)
        raise ValueError("Tangential stress singularity.")
        
    term1 = -z / (R ** 3)
    term2 = 1.0 / (R * (R + z))
    return (P * (1.0 - 2.0 * nu) / (2.0 * math.pi)) * (term1 + term2)


def shear_stress_point_load(P: float, r: float, z: float) -> float:
    """Compute vertical-radial shear stress (tau_rz) under point load P.

    Equation: tau_rz = 3 * P * r * z^2 / (2 * pi * R^5)
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(z, "z")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
        
    R = math.sqrt(r * r + z * z)
    if is_near_zero(R):
        raise ValueError("Point-load shear stress singularity at exact load origin (R=0).")
        
    return (3.0 * P * r * (z ** 2)) / (2.0 * math.pi * (R ** 5))


def surface_deflection_point_load(P: float, r: float, E: float, nu: float) -> float:
    """Compute vertical deflection (w) on elastic half-space surface (z=0) under point load P.

    Equation: w = P * (1 - nu^2) / (pi * E * r)
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(E, "E")
    validate_finite_number(nu, "nu")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if E <= 0.0:
        raise ValueError("Elastic modulus E must be positive.")
    if nu <= 0.0 or nu >= 0.5:
        raise ValueError(f"Poisson's ratio nu must be in the range (0.0, 0.5). Got: {nu}.")
    if is_near_zero(r):
        raise ValueError("Deflection singularity at origin r=0 for point load.")
        
    return (P * (1.0 - nu * nu)) / (math.pi * E * r)


def deflection_point_load_depth(P: float, r: float, z: float, E: float, nu: float) -> float:
    """Compute vertical deflection (w) at depth z under point load P.

    Equation: w = P * (1 + nu) / (2 * pi * E * R) * (2 * (1 - nu) + z^2 / R^2)
    Reference: Boussinesq (1885)
    """
    validate_finite_number(P, "P")
    validate_finite_number(r, "r")
    validate_finite_number(z, "z")
    validate_finite_number(E, "E")
    validate_finite_number(nu, "nu")
    
    if P <= 0.0:
        raise ValueError("Point load P must be positive.")
    if E <= 0.0:
        raise ValueError("Elastic modulus E must be positive.")
    if nu <= 0.0 or nu >= 0.5:
        raise ValueError(f"Poisson's ratio nu must be in the range (0.0, 0.5). Got: {nu}.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
        
    R = math.sqrt(r * r + z * z)
    if is_near_zero(R):
        raise ValueError("Deflection singularity at origin R=0 for point load.")
        
    term1 = 2.0 * (1.0 - nu)
    term2 = (z * z) / (R * R)
    return (P * (1.0 + nu)) / (2.0 * math.pi * E * R) * (term1 + term2)


def vertical_stress_circular_axis(q: float, a: float, z: float) -> float:
    """Compute vertical stress (sigma_z) along circular load axis (centerline).

    Equation: sigma_z = q * (1 - z^3 / (a^2 + z^2)^1.5)
    Reference: Love (1929) / Huang eq. 2.1
    """
    validate_finite_number(q, "q")
    validate_finite_number(a, "a")
    validate_finite_number(z, "z")
    
    if q <= 0.0:
        raise ValueError("Circular pressure q must be positive.")
    if a <= 0.0:
        raise ValueError("Tire contact radius a must be positive.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
        
    if is_near_zero(z):
        return float(q)
        
    return q * (1.0 - (z ** 3) / ((a * a + z * z) ** 1.5))


def vertical_deflection_circular_axis(q: float, a: float, E: float, nu: float, z: float = 0.0) -> float:
    """Compute vertical deflection (w) along circular load axis (centerline) at depth z.

    Equation: w = (1+nu)*q*a/E * [ a/sqrt(a^2+z^2) + 2(1-nu)*(sqrt(1+z^2/a^2) - z/a) ]
    Reference: Huang eq. 2.11
    """
    validate_finite_number(q, "q")
    validate_finite_number(a, "a")
    validate_finite_number(E, "E")
    validate_finite_number(nu, "nu")
    validate_finite_number(z, "z")
    
    if q <= 0.0:
        raise ValueError("Circular pressure q must be positive.")
    if a <= 0.0:
        raise ValueError("Tire contact radius a must be positive.")
    if E <= 0.0:
        raise ValueError("Elastic modulus E must be positive.")
    if nu <= 0.0 or nu >= 0.5:
        raise ValueError(f"Poisson's ratio nu must be in the range (0.0, 0.5). Got: {nu}.")
    if z < 0.0:
        raise ValueError("Depth z must be non-negative.")
        
    term1 = z / math.sqrt(a * a + z * z)
    term2 = 2.0 * (1.0 - nu) * (math.sqrt(1.0 + (z * z) / (a * a)) - z / a)
    return ((1.0 + nu) * q * a / E) * (term1 + term2)
