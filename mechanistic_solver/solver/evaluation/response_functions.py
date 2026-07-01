"""Burmister radial-parameter-domain response functions for multilayer systems.

Converts solved coefficients into integrand callables for Hankel integration.
Uses negative-exponential coordinate scaling for high-frequency stability.
"""
from __future__ import annotations

import math
from typing import Callable

from mechanistic_solver.core.constants import SMALL_RADIAL_PARAMETER
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.matrix.transfer_matrix import TransferMatrixBuilder
from mechanistic_solver.solver.matrix.linear_solver import solve_system


def get_layer_coefficients_at_m(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    m: float
) -> list[dict[str, float]]:
    """Solve the boundary conditions system for a given radial parameter m."""
    m_val = max(m, SMALL_RADIAL_PARAMETER)
    
    # Construct a hashable key for layer system
    layers_key = tuple((float(l.thickness or 0.0), float(l.elastic_modulus), float(l.poisson_ratio)) for l in layer_system.layers)
    subgrade_key = (float(layer_system.subgrade.elastic_modulus), float(layer_system.subgrade.poisson_ratio))
    system_key = (layers_key, subgrade_key)
    
    cache_key = (system_key, float(load_radius_m), float(pressure_pa), float(m_val))
    
    from mechanistic_solver.core.cache import global_cache
    cached = global_cache.get("burmister_coefficients", cache_key)
    if cached is not None:
        return cached
        
    builder = TransferMatrixBuilder()
    coeff_sys = builder.build_for_layer_system(
        layer_system=layer_system,
        radial_parameter=m_val,
        wheel_load_radius_m=load_radius_m,
        contact_pressure_pa=pressure_pa
    )
    
    # Solve system A * x = B
    try:
        x = solve_system(coeff_sys.A, coeff_sys.B)
    except Exception:
        # Fallback to zero vector if solver fails
        dim = coeff_sys.shape[0]
        x = [0.0] * dim
        
    n_finite = len(layer_system.layers)
    coeffs_list = []
    
    for i in range(n_finite):
        coeffs_list.append({
            "A": float(x[4*i]),
            "B": float(x[4*i+1]),
            "C": float(x[4*i+2]),
            "D": float(x[4*i+3])
        })
    # Subgrade
    coeffs_list.append({
        "A": float(x[4*n_finite]),
        "B": 0.0,
        "C": float(x[4*n_finite+1]),
        "D": 0.0
    })
    
    global_cache.set("burmister_coefficients", cache_key, coeffs_list)
    return coeffs_list


def build_sigma_z_function(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    z_m: float
) -> Callable[[float], float]:
    """Build vertical stress integrand function (without J0 weight)."""
    layer_idx = layer_system.get_layer_index_at_depth(z_m * 1000.0)
    h_top = layer_system.get_layer_top_depth(layer_idx) / 1000.0
    z_i = z_m - h_top
    
    is_subgrade = (layer_idx == len(layer_system.layers))
    if is_subgrade:
        nu_i = layer_system.subgrade.poisson_ratio
        h_i = 0.0
    else:
        nu_i = layer_system.layers[layer_idx].poisson_ratio
        h_i = float(layer_system.layers[layer_idx].thickness) / 1000.0

    def func(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]
        
        # Exponential factors using negative-exponential scaling
        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))
        
        term = (
            m_val * (c["A"] * exp_neg + c["B"] * exp_pos)
            + (m_val * z_i - 2.0 * (1.0 - nu_i)) * c["C"] * exp_neg
            + (m_val * z_i + 2.0 * (1.0 - nu_i)) * c["D"] * exp_pos
        )
        return m_val * term

    return func


def build_tau_rz_function(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    z_m: float
) -> Callable[[float], float]:
    """Build shear stress integrand function (without J1 weight)."""
    layer_idx = layer_system.get_layer_index_at_depth(z_m * 1000.0)
    h_top = layer_system.get_layer_top_depth(layer_idx) / 1000.0
    z_i = z_m - h_top
    
    is_subgrade = (layer_idx == len(layer_system.layers))
    if is_subgrade:
        nu_i = layer_system.subgrade.poisson_ratio
        h_i = 0.0
    else:
        nu_i = layer_system.layers[layer_idx].poisson_ratio
        h_i = float(layer_system.layers[layer_idx].thickness) / 1000.0

    def func(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]
        
        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))
        
        # Equilibrium-consistent shear kernel S_tau = -d(term_sigma)/dz, i.e.
        # term_tau = m*A*e- - m*B*e+ + (m*z-(3-2nu))*C*e- - (m*z+(3-2nu))*D*e+.
        term = (
            m_val * (c["A"] * exp_neg - c["B"] * exp_pos)
            + (m_val * z_i - (3.0 - 2.0 * nu_i)) * c["C"] * exp_neg
            - (m_val * z_i + (3.0 - 2.0 * nu_i)) * c["D"] * exp_pos
        )
        return m_val * term

    return func


def build_vertical_displacement_function(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    z_m: float
) -> Callable[[float], float]:
    """Build vertical deflection integrand function (without J0 weight)."""
    layer_idx = layer_system.get_layer_index_at_depth(z_m * 1000.0)
    h_top = layer_system.get_layer_top_depth(layer_idx) / 1000.0
    z_i = z_m - h_top
    
    is_subgrade = (layer_idx == len(layer_system.layers))
    if is_subgrade:
        nu_i = layer_system.subgrade.poisson_ratio
        E_i = layer_system.subgrade.elastic_modulus * 1e6
        h_i = 0.0
    else:
        nu_i = layer_system.layers[layer_idx].poisson_ratio
        E_i = layer_system.layers[layer_idx].elastic_modulus * 1e6
        h_i = float(layer_system.layers[layer_idx].thickness) / 1000.0

    E_star = (1.0 + nu_i) / E_i

    def func(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]
        
        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))
        
        # Love-function-consistent vertical displacement kernel:
        #   term_w = m*A*e- - m*B*e+ + (m*z-1)*C*e- - (m*z+1)*D*e+
        # (the C/D constant is 1, NOT 2-4nu; verified against Boussinesq w0).
        term = (
            m_val * (c["A"] * exp_neg - c["B"] * exp_pos)
            + (m_val * z_i - 1.0) * c["C"] * exp_neg
            - (m_val * z_i + 1.0) * c["D"] * exp_pos
        )
        return E_star * term

    return func


def build_sigma_r_functions(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    z_m: float
) -> tuple[Callable[[float], float], Callable[[float], float]]:
    """Build functions f0(m) and f1(m) for radial stress calculation."""
    layer_idx = layer_system.get_layer_index_at_depth(z_m * 1000.0)
    h_top = layer_system.get_layer_top_depth(layer_idx) / 1000.0
    z_i = z_m - h_top
    
    is_subgrade = (layer_idx == len(layer_system.layers))
    if is_subgrade:
        nu_i = layer_system.subgrade.poisson_ratio
        h_i = 0.0
    else:
        nu_i = layer_system.layers[layer_idx].poisson_ratio
        h_i = float(layer_system.layers[layer_idx].thickness) / 1000.0

    # Radial-stress split sigma_r = INT f0 J0 dm - (1/r) INT f1 J1 dm, with the
    # Love-function-consistent kernels (compression-positive convention):
    #   f0 = -m[ (mA + (mz-(4-2nu))C)e- + (mB + (mz+(4-2nu))D)e+ ]
    #   f1 = -[ (mA + (mz-4(1-nu))C)e- + (mB + (mz+4(1-nu))D)e+ ]
    def f0(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]

        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))

        term = (
            (m_val * c["A"] + (m_val * z_i - (4.0 - 2.0 * nu_i)) * c["C"]) * exp_neg
            + (m_val * c["B"] + (m_val * z_i + (4.0 - 2.0 * nu_i)) * c["D"]) * exp_pos
        )
        return -m_val * term

    def f1(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]

        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))

        term = (
            (m_val * c["A"] + (m_val * z_i - 4.0 * (1.0 - nu_i)) * c["C"]) * exp_neg
            + (m_val * c["B"] + (m_val * z_i + 4.0 * (1.0 - nu_i)) * c["D"]) * exp_pos
        )
        return -term

    return f0, f1


def build_sigma_theta_functions(
    layer_system: LayerSystem,
    load_radius_m: float,
    pressure_pa: float,
    z_m: float
) -> tuple[Callable[[float], float], Callable[[float], float]]:
    """Build functions g0(m) and f1(m) for tangential stress calculation."""
    layer_idx = layer_system.get_layer_index_at_depth(z_m * 1000.0)
    h_top = layer_system.get_layer_top_depth(layer_idx) / 1000.0
    z_i = z_m - h_top
    
    is_subgrade = (layer_idx == len(layer_system.layers))
    if is_subgrade:
        nu_i = layer_system.subgrade.poisson_ratio
        h_i = 0.0
    else:
        nu_i = layer_system.layers[layer_idx].poisson_ratio
        h_i = float(layer_system.layers[layer_idx].thickness) / 1000.0

    def g0(m: float) -> float:
        m_val = max(m, SMALL_RADIAL_PARAMETER)
        coeffs = get_layer_coefficients_at_m(layer_system, load_radius_m, pressure_pa, m_val)
        c = coeffs[layer_idx]
        
        exp_neg = math.exp(-m_val * z_i)
        exp_pos = 0.0 if is_subgrade else math.exp(-m_val * (h_i - z_i))

        # g0 = 2*nu*m*(C*e- - D*e+)  (Love-function consistent, compression-positive)
        return 2.0 * nu_i * m_val * (c["C"] * exp_neg - c["D"] * exp_pos)

    _, f1 = build_sigma_r_functions(layer_system, load_radius_m, pressure_pa, z_m)
    return g0, f1
