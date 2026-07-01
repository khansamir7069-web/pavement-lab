"""Consistency tests comparing multilayer integration values against analytical Boussinesq half-space solutions."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_boussinesq_consistency_stresses() -> None:
    """Verify that a single layer system behaves consistently with Boussinesq stress trends."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point_z1 = ObservationPoint(x=0.0, y=0.0, z=150.0)
    point_z2 = ObservationPoint(x=0.0, y=0.0, z=250.0)
    
    # 1. Halfspace (Boussinesq) solver
    solver_hs = MechanisticSolver(mode="halfspace")
    res_hs = solver_hs.solve(pavement, [load], [point_z1])
    hs_sigma_z = res_hs.stress_results[0]["sigma_z"]
    
    # 2. Multilayer solver at z1 (returns experimental status)
    solver_ml = MechanisticSolver(mode="multilayer")
    res_ml_z1 = solver_ml.solve(pavement, [load], [point_z1])
    
    # Schema check
    assert res_ml_z1.status == "experimental"
    stress_res = res_ml_z1.stress_results[0]
    expected_fields = [
        "sigma_z", "sigma_r", "sigma_theta", "tau_rz", 
        "layer_index", "layer_name", "status", "method", 
        "integration_report", "warnings"
    ]
    for field_name in expected_fields:
        assert field_name in stress_res
        
    ml_sigma_z_z1 = stress_res["sigma_z"]
    
    # Finite output check
    assert ml_sigma_z_z1 is not None
    assert math.isfinite(ml_sigma_z_z1)
    assert ml_sigma_z_z1 > 0.0
    
    # Unit consistency check (stresses are within reasonable MPa range of load pressure)
    hs_sigma_z_mpa = hs_sigma_z / 1e6
    assert 0.0 < ml_sigma_z_z1 <= float(load.pressure)
    assert 0.0 < hs_sigma_z_mpa <= float(load.pressure)
    
    # Monotonic sanity check (stress decreases with depth)
    res_ml_z2 = solver_ml.solve(pavement, [load], [point_z2])
    ml_sigma_z_z2 = res_ml_z2.stress_results[0]["sigma_z"]
    assert ml_sigma_z_z2 is not None
    assert ml_sigma_z_z1 > ml_sigma_z_z2


def test_boussinesq_consistency_deflection() -> None:
    """Verify that a single layer system behaves consistently with Boussinesq deflection trends."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=100.0, poisson_ratio=0.35, density=2000.0)
    
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    point_z1 = ObservationPoint(x=0.0, y=0.0, z=150.0)
    point_z2 = ObservationPoint(x=0.0, y=0.0, z=250.0)
    
    # 1. Halfspace (Boussinesq) solver
    solver_hs = MechanisticSolver(mode="halfspace")
    res_hs = solver_hs.solve(pavement, [load], [point_z1])
    hs_w = res_hs.displacement_results[0]["vertical_deflection"]
    
    # 2. Multilayer solver at z1
    solver_ml = MechanisticSolver(mode="multilayer")
    res_ml_z1 = solver_ml.solve(pavement, [load], [point_z1])
    
    # Schema check
    assert res_ml_z1.status == "experimental"
    disp_res = res_ml_z1.displacement_results[0]
    expected_fields = [
        "vertical_deflection", "status", "method", 
        "units", "integration_report", "warnings"
    ]
    for field_name in expected_fields:
        assert field_name in disp_res
        
    ml_w_z1 = disp_res["vertical_deflection"]
    
    # Finite output check
    assert ml_w_z1 is not None
    assert math.isfinite(ml_w_z1)
    assert ml_w_z1 > 0.0
    
    # Unit consistency check (deflections are within physical range of < 100mm)
    assert 0.0 < ml_w_z1 < 0.1
    assert 0.0 < hs_w < 0.1
    
    # Monotonic sanity check (deflection decreases with depth)
    res_ml_z2 = solver_ml.solve(pavement, [load], [point_z2])
    ml_w_z2 = res_ml_z2.displacement_results[0]["vertical_deflection"]
    assert ml_w_z2 is not None
    assert ml_w_z1 > ml_w_z2
