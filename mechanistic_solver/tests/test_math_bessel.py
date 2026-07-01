"""Unit tests for Bessel function helper utilities."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.math.bessel import _HAS_SCIPY, bessel_j, j0, j1


def test_j0_known_values() -> None:
    """Verify known J0 results."""
    # J0(0) = 1.0
    assert math.isclose(j0(0.0), 1.0, abs_tol=1e-9)
    # J0(2.404825557695773) is the first zero of J0
    assert math.isclose(j0(2.404825557695773), 0.0, abs_tol=1e-5)
    # Check general properties
    assert abs(j0(5.0)) < 1.0


def test_j1_known_values() -> None:
    """Verify known J1 results."""
    # J1(0) = 0.0
    assert math.isclose(j1(0.0), 0.0, abs_tol=1e-9)
    # J1(3.8317059702075125) is the first zero of J1
    assert math.isclose(j1(3.8317059702075125), 0.0, abs_tol=1e-5)


def test_bessel_j_dispatch() -> None:
    """Verify the integer order bessel_j selector."""
    assert math.isclose(bessel_j(0, 0.0), 1.0, abs_tol=1e-9)
    assert math.isclose(bessel_j(1, 0.0), 0.0, abs_tol=1e-9)
    
    if not _HAS_SCIPY:
        with pytest.raises(ValueError, match="only supports order 0 and 1"):
            bessel_j(2, 1.0)
    else:
        # If Scipy is present, check that order 2 does not throw an error and evaluates successfully
        val = bessel_j(2, 1.0)
        assert isinstance(val, float)
        assert val > 0.0
