"""Unit tests for the HankelIntegrator and convergence checks."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.solver.integration.hankel_integrator import HankelIntegrator
from mechanistic_solver.solver.integration.convergence import verify_convergence


def test_hankel_integrator_order0() -> None:
    """Verify integration of J0(m) from 0 to 10.0."""
    integrator = HankelIntegrator()
    # f(m) = 1.0 -> integrates J0(m*r)
    func = lambda m: 1.0
    res = integrator.integrate_order0(func, r=2.0, upper_limit=10.0)
    
    assert res.converged
    assert isinstance(res.value, float)
    assert verify_convergence(res, 1e-6)


def test_hankel_integrator_order1() -> None:
    """Verify integration of J1(m) from 0 to 10.0."""
    integrator = HankelIntegrator()
    func = lambda m: 1.0
    res = integrator.integrate_order1(func, r=2.0, upper_limit=10.0)
    
    assert res.converged
    assert isinstance(res.value, float)


def test_integration_result_serialization() -> None:
    """Verify serialization of IntegrationResult diagnostics."""
    integrator = HankelIntegrator()
    func = lambda m: math.exp(-m)
    res = integrator.integrate_order0(func, r=0.0, upper_limit=20.0)
    
    data = res.to_dict()
    assert data["converged"] is True
    assert "value" in data
    assert "estimated_error" in data
