"""Multilayer stress evaluator using Hankel Integration.

Computes vertical, radial, tangential, and shear stresses at Point (r, z) in MPa.
"""
from __future__ import annotations

import math
from typing import Any

from mechanistic_solver.core.models import ObservationPoint, WheelLoad
from mechanistic_solver.solver.integration.hankel_integrator import HankelIntegrator
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.evaluation.response_functions import (
    build_sigma_z_function,
    build_tau_rz_function,
    build_sigma_r_functions,
    build_sigma_theta_functions,
)


def evaluate_stress(
    layer_system: LayerSystem,
    coefficients: Any,  # Kept for backward compatibility interface
    load: WheelLoad,
    point: ObservationPoint,
    boundary_conditions: BoundaryConditionSet,
    integration_settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate stress tensor at observation point (x, y, z) in MPa."""
    # Radial coordinate and evaluation depth in meters
    r_m = math.sqrt(point.x * point.x + point.y * point.y) / 1000.0
    z_m = point.z / 1000.0
    
    a = float(load.radius) / 1000.0
    q = float(load.pressure) * 1e6
    
    integrator = HankelIntegrator()
    warnings: list[str] = []
    integration_reports: dict[str, Any] = {}
    
    layer_idx = layer_system.get_layer_index_at_depth(point.z)
    target_layer = layer_system.subgrade if layer_idx == len(layer_system.layers) else layer_system.layers[layer_idx]
    
    # 1. Vertical stress (sigma_z)
    try:
        func_z = build_sigma_z_function(layer_system, a, q, z_m)
        res_z = integrator.integrate_order0(func_z, r_m, kernel_length=a)
        sigma_z = res_z.value / 1e6  # Pa -> MPa
        integration_reports["sigma_z"] = res_z.to_dict()
        warnings.extend(res_z.warnings)
    except Exception as e:
        sigma_z = None
        warnings.append(f"Vertical stress integration failed: {e}")
        
    # 2. Shear stress (tau_rz)
    try:
        func_tau = build_tau_rz_function(layer_system, a, q, z_m)
        res_tau = integrator.integrate_order1(func_tau, r_m, kernel_length=a)
        tau_rz = res_tau.value / 1e6
        integration_reports["tau_rz"] = res_tau.to_dict()
        warnings.extend(res_tau.warnings)
    except Exception as e:
        tau_rz = None
        warnings.append(f"Shear stress integration failed: {e}")

    # 3. Radial (sigma_r) and Tangential (sigma_theta) stresses
    try:
        f0, f1 = build_sigma_r_functions(layer_system, a, q, z_m)
        g0, _ = build_sigma_theta_functions(layer_system, a, q, z_m)
        
        if r_m > 1e-6:
            res_f0 = integrator.integrate_order0(f0, r_m, kernel_length=a)
            res_f1 = integrator.integrate_order1(f1, r_m, kernel_length=a)
            res_g0 = integrator.integrate_order0(g0, r_m, kernel_length=a)
            
            sigma_r = (res_f0.value - res_f1.value / r_m) / 1e6
            sigma_theta = (res_g0.value + res_f1.value / r_m) / 1e6
            
            integration_reports["sigma_r_f0"] = res_f0.to_dict()
            integration_reports["sigma_r_f1"] = res_f1.to_dict()
            integration_reports["sigma_theta_g0"] = res_g0.to_dict()
            
            warnings.extend(res_f0.warnings)
            warnings.extend(res_f1.warnings)
            warnings.extend(res_g0.warnings)
        else:
            # Special case for centerline r=0
            def integrand_r0(m: float) -> float:
                return f0(m) - 0.5 * m * f1(m)
                
            def integrand_t0(m: float) -> float:
                return g0(m) + 0.5 * m * f1(m)
                
            res_r0 = integrator.integrate_order0(integrand_r0, 0.0, kernel_length=a)
            res_t0 = integrator.integrate_order0(integrand_t0, 0.0, kernel_length=a)
            
            sigma_r = res_r0.value / 1e6
            sigma_theta = res_t0.value / 1e6
            
            integration_reports["sigma_r_r0"] = res_r0.to_dict()
            integration_reports["sigma_theta_t0"] = res_t0.to_dict()
            
            warnings.extend(res_r0.warnings)
            warnings.extend(res_t0.warnings)
    except Exception as e:
        sigma_r = None
        sigma_theta = None
        warnings.append(f"Radial/tangential stresses integration failed: {e}")

    status = "experimental"
    if sigma_z is None or sigma_r is None or sigma_theta is None or tau_rz is None:
        status = "partial"
        
    return {
        "sigma_z": sigma_z,
        "sigma_r": sigma_r,
        "sigma_theta": sigma_theta,
        "tau_rz": tau_rz,
        "layer_index": layer_idx,
        "layer_name": target_layer.name,
        "status": status,
        "method": "burmister_hankel_multilayer",
        "integration_report": integration_reports,
        "warnings": list(set(warnings))
    }
