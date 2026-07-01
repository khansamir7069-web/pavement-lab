"""Regression tests pinning the in-house solver to IITPAVE / Boussinesq physics.

These tests guard the mathematically-derived corrections applied to the
Burmister kernel (circular-load Hankel normalisation, the equilibrium-consistent
shear kernel, the Love-function-consistent radial/tangential stress and vertical
displacement kernels) and the adaptive Hankel-integration convergence handling.

No empirical scaling or calibration constants are used anywhere: every expected
value comes either from a closed-form Boussinesq half-space solution or from the
published IITPAVE benchmark.
"""
from __future__ import annotations

import math

import pytest

from mechanistic_solver.core.constants import SMALL_RADIAL_PARAMETER
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.math.bessel import j1
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.solver.integration.hankel_integrator import HankelIntegrator
from mechanistic_solver.solver.matrix.boundary_equations import assemble_bonded_system
from mechanistic_solver.solver.matrix.layer_system import LayerSystem


# --------------------------------------------------------------------------- #
# Circular-load Hankel normalisation
# --------------------------------------------------------------------------- #
def _simple_layer_system() -> LayerSystem:
    layers = [Layer("BC", 100.0, 3000.0, 0.35, 2400.0)]
    subgrade = Layer("Subgrade", None, 50.0, 0.35, 1800.0)
    return LayerSystem(layers, subgrade)


def test_circular_load_transform_matches_hankel_convention() -> None:
    """B[0] must equal the order-0 Hankel transform q*a*J1(m*a)/m of the load."""
    ls = _simple_layer_system()
    a = 0.10662          # m
    q = 0.56e6           # Pa
    for m in (0.5, 1.0, 5.0, 20.0, 75.0):
        _, B = assemble_bonded_system(ls, m, a, q)
        expected = (q * a * j1(m * a)) / m
        assert B[0] == pytest.approx(expected, rel=1e-12)


def test_circular_load_total_force_consistency() -> None:
    """The transform must be consistent with total load P = pi * a^2 * q.

    The m->0 limit of the order-0 Hankel transform of the contact pressure is
    INT_0^inf p(r) r dr = q*a^2/2, and the resultant wheel force is 2*pi times
    that, i.e. pi*a^2*q.  With P = 20 kN, q = 0.56 MPa the benchmark radius
    a = 106.62 mm is exactly the value that closes P = pi*a^2*q.
    """
    ls = _simple_layer_system()
    a = 0.10662          # m
    q = 0.56e6           # Pa

    # Small-m finite-limit branch value.
    _, B = assemble_bonded_system(ls, SMALL_RADIAL_PARAMETER, a, q)
    assert B[0] == pytest.approx(0.5 * q * a * a, rel=1e-9)

    total_force = 2.0 * math.pi * B[0]
    assert total_force == pytest.approx(math.pi * a * a * q, rel=1e-9)
    assert total_force == pytest.approx(20.0e3, rel=2e-3)  # ~20 kN wheel load


def test_circular_load_small_m_finite_limit_is_continuous() -> None:
    """The small-m limit branch must join the general formula without a jump."""
    ls = _simple_layer_system()
    a = 0.10662
    q = 0.56e6

    # Exactly at the threshold the analytic limit branch is used ...
    _, B_limit = assemble_bonded_system(ls, SMALL_RADIAL_PARAMETER, a, q)
    # ... and just above it the general q*a*J1(m*a)/m formula is used; the two
    # must agree because J1(m*a) ~ m*a/2 as m -> 0  =>  q*a*J1/m -> q*a^2/2.
    m_above = SMALL_RADIAL_PARAMETER * 10.0
    _, B_general = assemble_bonded_system(ls, m_above, a, q)
    assert B_limit[0] == pytest.approx(0.5 * q * a * a, rel=1e-9)
    assert B_general[0] == pytest.approx(0.5 * q * a * a, rel=1e-6)


# --------------------------------------------------------------------------- #
# Homogeneous stack must reduce to the closed-form Boussinesq half-space
# --------------------------------------------------------------------------- #
def test_homogeneous_stack_reduces_to_boussinesq() -> None:
    """A single-material stack must reproduce the Boussinesq half-space fields."""
    E, nu, q, a = 50.0, 0.35, 0.56, 106.62
    layers = [Layer("L1", 400.0, E, nu, 2000.0), Layer("L2", 400.0, E, nu, 2000.0)]
    subgrade = Layer("Subgrade", None, E, nu, 1800.0)
    pavement = Pavement(layers=layers, subgrade=subgrade)
    load = WheelLoad(wheel_load=20.0, pressure=q, radius=a)

    # Surface deflection: w0 = 2*q*a*(1-nu^2)/E (uniform circular load on half-space)
    w0 = 2.0 * (q * 1e6) * (a / 1000.0) * (1.0 - nu * nu) / (E * 1e6)
    pts = [ObservationPoint(0.0, 0.0, 0.0),
           ObservationPoint(0.0, 0.0, 100.0),
           ObservationPoint(0.0, 0.0, 200.0)]
    resp = MechanisticSolver(mode="multilayer").solve(pavement, [load], pts)

    assert resp.surface_deflection == pytest.approx(w0, rel=0.01)

    # Vertical stress on axis: sigma_z = q*(1 - z^3/(a^2+z^2)^1.5) (magnitude).
    for rec in resp.stress_results:
        z = pts[rec["point_index"]].z
        if z <= 0.0:
            continue
        zm, am = z / 1000.0, a / 1000.0
        cf = (q) * (1.0 - zm ** 3 / (am * am + zm * zm) ** 1.5)
        assert abs(rec["sigma_z"]) == pytest.approx(cf, rel=0.02)


# --------------------------------------------------------------------------- #
# Published IITPAVE benchmark
# --------------------------------------------------------------------------- #
def _benchmark_pavement() -> Pavement:
    layers = [
        Layer("BC", 40.0, 3000.0, 0.35, 2400.0),
        Layer("DBM", 160.0, 3000.0, 0.35, 2400.0),
        Layer("WMM", 250.0, 450.0, 0.35, 2200.0),
        Layer("GSB", 230.0, 200.0, 0.35, 2000.0),
    ]
    subgrade = Layer("Subgrade", None, 50.0, 0.35, 1800.0)
    return Pavement(layers=layers, subgrade=subgrade)


def test_iitpave_benchmark_case() -> None:
    """RoadX must match the published IITPAVE benchmark within tolerance.

    IITPAVE expected (P=20 kN, q=0.56 MPa, a=106.62 mm):
      surface deflection z=0      = 0.2030 mm
      epsilon_t  z=200 mm         = 72.82  microstrain (tensile)
      epsilon_v  z=680 mm (subgr) = 121.8  microstrain (compressive)

    Tolerances: deflection 10%, epsilon_t 15%, epsilon_v 15%.  Magnitudes are
    compared because the solver uses a compression-positive convention while
    IITPAVE reports tension-positive strains.
    """
    pavement = _benchmark_pavement()
    load = WheelLoad(wheel_load=20.0, pressure=0.56, radius=106.62)
    pts = [
        ObservationPoint(0.0, 0.0, 0.0),     # surface deflection
        ObservationPoint(0.0, 0.0, 200.0),   # bottom of bituminous (BC+DBM)
        ObservationPoint(0.0, 0.0, 680.0),   # top of subgrade
    ]
    resp = MechanisticSolver(mode="multilayer").solve(pavement, [load], pts)

    deflection_mm = resp.surface_deflection * 1000.0

    s200 = resp.strain_results[1]
    eps_t_micro = max(abs(s200.get("epsilon_r") or 0.0), abs(s200.get("epsilon_t") or 0.0)) * 1e6

    s680 = resp.strain_results[2]
    eps_v_micro = abs(s680.get("epsilon_z") or 0.0) * 1e6

    assert deflection_mm == pytest.approx(0.2030, rel=0.10)
    assert eps_t_micro == pytest.approx(72.82, rel=0.15)
    assert eps_v_micro == pytest.approx(121.8, rel=0.15)


# --------------------------------------------------------------------------- #
# Hankel integration convergence diagnostics
# --------------------------------------------------------------------------- #
def test_hankel_convergence_diagnostic_on_divergent_tail() -> None:
    """A non-decaying integrand must be reported as NON-converged, not hidden."""
    integrator = HankelIntegrator()
    # On the axis (r=0) J0(0)=1, so a constant integrand has a tail that never
    # decays: INT_0^L 1 dm = L diverges.  The integrator must flag this.
    res = integrator.integrate_order0(lambda m: 1.0, r=0.0)
    assert res.converged is False
    assert res.warnings, "Non-convergence must surface an explicit diagnostic warning."
    assert any("did not converge" in w for w in res.warnings)


def test_hankel_convergence_on_decaying_tail() -> None:
    """A well-behaved exponentially decaying integrand must converge cleanly."""
    integrator = HankelIntegrator()
    res = integrator.integrate_order0(lambda m: math.exp(-m), r=0.0, kernel_length=0.1)
    assert res.converged is True
    assert res.value == pytest.approx(1.0, rel=1e-4)  # INT_0^inf e^-m dm = 1
    assert not any("did not converge" in w for w in res.warnings)
