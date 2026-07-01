"""Convergence checks and relative/absolute error validation utilities."""
from __future__ import annotations

import math
from mechanistic_solver.solver.integration.hankel_integrator import IntegrationResult


def check_relative_absolute_tolerances(
    value: float,
    expected: float,
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-4
) -> bool:
    """Verify if value matches expected within absolute and relative tolerances."""
    diff = abs(value - expected)
    if diff <= abs_tol:
        return True
    if expected != 0.0 and (diff / abs(expected)) <= rel_tol:
        return True
    return False


def verify_convergence(result: IntegrationResult, tolerance: float) -> bool:
    """Analyze integration diagnostic outputs to verify convergence status."""
    if not result.converged:
        return False
    if math.isnan(result.value) or math.isinf(result.value):
        return False
    if result.estimated_error > tolerance * 100.0:
        return False
    return True
