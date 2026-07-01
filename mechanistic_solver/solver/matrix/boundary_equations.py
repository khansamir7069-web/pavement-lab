"""Assembles Burmister boundary condition equations for layered systems.

Defines coefficient matrix A and boundary loading vector B elements.
Uses local coordinate scaling with negative exponentials to prevent overflow.
All equations are derived in SI units (meters, Pascals).
"""
from __future__ import annotations

import math
import numpy as np

from mechanistic_solver.core.constants import SMALL_RADIAL_PARAMETER
from mechanistic_solver.math.bessel import j1
from mechanistic_solver.solver.matrix.layer_system import LayerSystem


def assemble_bonded_system(
    layer_system: LayerSystem,
    radial_parameter: float,
    wheel_load_radius_m: float,
    contact_pressure_pa: float
) -> tuple[np.ndarray, np.ndarray]:
    """Assemble the system matrix A and right-hand side vector B.

    Uses exponential scaling to keep all matrix coefficients bounded between 0 and 1.
    """
    m = float(radial_parameter)
    a = float(wheel_load_radius_m)
    q = float(contact_pressure_pa)
    
    n = len(layer_system.layers) + 1
    dim = 4 * n - 2
    
    A = np.zeros((dim, dim), dtype=np.float64)
    B = np.zeros(dim, dtype=np.float64)
    
    # Pre-calculate E* parameters (1+nu)/E for each layer
    E_star = []
    for layer in layer_system.layers:
        E_star.append((1.0 + layer.poisson_ratio) / (layer.elastic_modulus * 1e6))
    E_star.append((1.0 + layer_system.subgrade.poisson_ratio) / (layer_system.subgrade.elastic_modulus * 1e6))
    
    # Reference modular scale to keep displacement rows conditioned
    E_ref = E_star[0]
    
    # -------------------------------------------------------------
    # 1. Surface Boundary Equations (z_1 = 0)
    # -------------------------------------------------------------
    nu1 = layer_system.layers[0].poisson_ratio
    h1 = float(layer_system.layers[0].thickness) / 1000.0
    
    # exp(-m * h1)
    exp_h1 = math.exp(-m * h1) if m * h1 < 100.0 else 0.0
    
    # Row 0: Vertical stress: m * A_1 + m * B_1 * exp(-m*h1) - 2*(1-nu1)*C_1 + 2*(1-nu1)*D_1*exp(-m*h1) = loading
    A[0, 0] = m
    A[0, 1] = m * exp_h1
    A[0, 2] = -2.0 * (1.0 - nu1)
    A[0, 3] = 2.0 * (1.0 - nu1) * exp_h1
    
    # Surface vertical-stress loading term: the order-0 Hankel transform of a
    # uniform circular pressure q over radius a is  q * a * J1(m*a) / m.
    # Because the response integrands carry the inverse-transform weight m*dm
    # (see response_functions / hankel_integrator), the transformed load that
    # belongs on the right-hand side is exactly this quantity -- a single 1/m,
    # not 1/m^2.  As m -> 0, J1(m*a) ~ m*a/2, so the term tends to q*a^2/2.
    if abs(m) <= SMALL_RADIAL_PARAMETER:
        B[0] = 0.5 * q * a * a
    else:
        B[0] = (q * a * j1(m * a)) / m
        
    # Row 1: Shear stress free surface tau_rz(r,0)=0.
    # The equilibrium-consistent shear kernel is  term_tau = m*A*e- - m*B*e+
    #   + (m*z-(3-2*nu))*C*e- - (m*z+(3-2*nu))*D*e+   (derived from
    #   dsigma_z/dz + (1/r) d(r*tau_rz)/dr = 0, i.e. S_tau = -d(term_sigma)/dz).
    # Evaluated at the surface (z=0):
    A[1, 0] = m
    A[1, 1] = -m * exp_h1
    A[1, 2] = -(3.0 - 2.0 * nu1)
    A[1, 3] = -(3.0 - 2.0 * nu1) * exp_h1
    B[1] = 0.0
    
    # -------------------------------------------------------------
    # 2. Interface Continuity Equations
    # -------------------------------------------------------------
    for i in range(len(layer_system.layers)):
        h_i = float(layer_system.layers[i].thickness) / 1000.0
        nu_i = layer_system.layers[i].poisson_ratio
        
        # Next layer properties
        is_next_subgrade = (i + 1 == len(layer_system.layers))
        if is_next_subgrade:
            nu_next = layer_system.subgrade.poisson_ratio
            exp_next = 0.0
        else:
            nu_next = layer_system.layers[i+1].poisson_ratio
            h_next = float(layer_system.layers[i+1].thickness) / 1000.0
            exp_next = math.exp(-m * h_next) if m * h_next < 100.0 else 0.0
            
        exp_i = math.exp(-m * h_i) if m * h_i < 100.0 else 0.0
        
        # Modular ratios for conditioning displacement equations
        f_i = E_star[i] / E_ref
        f_next = E_star[i+1] / E_ref
        
        col_i = 4 * i
        col_next = 4 * (i + 1)
        r_start = 2 + 4 * i
        
        # a. Vertical Stress Continuity
        A[r_start, col_i] = m * exp_i
        A[r_start, col_i + 1] = m
        A[r_start, col_i + 2] = (m * h_i - 2.0 * (1.0 - nu_i)) * exp_i
        A[r_start, col_i + 3] = (m * h_i + 2.0 * (1.0 - nu_i))
        
        A[r_start, col_next] = -m
        if not is_next_subgrade:
            A[r_start, col_next + 1] = -m * exp_next
            A[r_start, col_next + 2] = 2.0 * (1.0 - nu_next)
            A[r_start, col_next + 3] = -2.0 * (1.0 - nu_next) * exp_next
        else:
            A[r_start, col_next + 1] = 2.0 * (1.0 - nu_next)
            
        # b. Shear Stress Continuity (equilibrium-consistent kernel, see Row 1)
        A[r_start + 1, col_i] = m * exp_i
        A[r_start + 1, col_i + 1] = -m
        A[r_start + 1, col_i + 2] = (m * h_i - (3.0 - 2.0 * nu_i)) * exp_i
        A[r_start + 1, col_i + 3] = -(m * h_i + (3.0 - 2.0 * nu_i))

        A[r_start + 1, col_next] = -m
        if not is_next_subgrade:
            A[r_start + 1, col_next + 1] = m * exp_next
            A[r_start + 1, col_next + 2] = (3.0 - 2.0 * nu_next)
            A[r_start + 1, col_next + 3] = (3.0 - 2.0 * nu_next) * exp_next
        else:
            A[r_start + 1, col_next + 1] = (3.0 - 2.0 * nu_next)

        # c. Vertical Displacement Continuity (scaled by E_ref), using the
        #    Love-consistent kernel term_w = m*A*e- - m*B*e+ + (m*z-1)*C*e- - (m*z+1)*D*e+
        A[r_start + 2, col_i] = f_i * m * exp_i
        A[r_start + 2, col_i + 1] = -f_i * m
        A[r_start + 2, col_i + 2] = f_i * (m * h_i - 1.0) * exp_i
        A[r_start + 2, col_i + 3] = -f_i * (m * h_i + 1.0)

        A[r_start + 2, col_next] = -f_next * m
        if not is_next_subgrade:
            A[r_start + 2, col_next + 1] = f_next * m * exp_next
            A[r_start + 2, col_next + 2] = f_next
            A[r_start + 2, col_next + 3] = f_next * exp_next
        else:
            A[r_start + 2, col_next + 1] = f_next

        # d. Radial Displacement Continuity (scaled by E_ref).
        #    2*mu*u_r = INT f1 J1 dm, so the u kernel is
        #    term_u = (m*A + (m*z-4(1-nu))C)e- + (m*B + (m*z+4(1-nu))D)e+.
        A[r_start + 3, col_i] = f_i * m * exp_i
        A[r_start + 3, col_i + 1] = f_i * m
        A[r_start + 3, col_i + 2] = f_i * (m * h_i - 4.0 * (1.0 - nu_i)) * exp_i
        A[r_start + 3, col_i + 3] = f_i * (m * h_i + 4.0 * (1.0 - nu_i))

        A[r_start + 3, col_next] = -f_next * m
        if not is_next_subgrade:
            A[r_start + 3, col_next + 1] = -f_next * m * exp_next
            A[r_start + 3, col_next + 2] = f_next * 4.0 * (1.0 - nu_next)
            A[r_start + 3, col_next + 3] = -f_next * 4.0 * (1.0 - nu_next) * exp_next
        else:
            A[r_start + 3, col_next + 1] = f_next * 4.0 * (1.0 - nu_next)
            
    return A, B
