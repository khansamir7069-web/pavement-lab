"""Unit tests for numerical integration utilities."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.math.integration import (
    integrate_adaptive_simpson,
    integrate_simpson,
    integrate_trapezoidal,
)


def test_integration_trapezoidal() -> None:
    """Verify trapezoidal integration of basic functions."""
    # integrate x^2 from 0 to 1 -> 1/3
    res = integrate_trapezoidal(lambda x: x * x, 0.0, 1.0, 1000)
    assert math.isclose(res, 1.0 / 3.0, abs_tol=1e-5)
    
    # integrate sin(x) from 0 to pi -> 2
    res_sin = integrate_trapezoidal(math.sin, 0.0, math.pi, 1000)
    assert math.isclose(res_sin, 2.0, abs_tol=1e-5)


def test_integration_simpson() -> None:
    """Verify Simpson integration of basic functions."""
    # integrate x^2 from 0 to 1 -> 1/3
    res = integrate_simpson(lambda x: x * x, 0.0, 1.0, 100)
    assert math.isclose(res, 1.0 / 3.0, abs_tol=1e-9)
    
    # Odd intervals raises error
    with pytest.raises(ValueError, match="requires an even number of intervals"):
        integrate_simpson(lambda x: x, 0.0, 1.0, 5)


def test_integration_adaptive_simpson() -> None:
    """Verify adaptive Simpson integration precision and bounds."""
    # integrate x^2 from 0 to 1 -> 1/3
    res = integrate_adaptive_simpson(lambda x: x * x, 0.0, 1.0, tolerance=1e-9)
    assert math.isclose(res, 1.0 / 3.0, abs_tol=1e-8)
    
    # integrate sin(x) from 0 to pi -> 2
    res_sin = integrate_adaptive_simpson(math.sin, 0.0, math.pi, tolerance=1e-9)
    assert math.isclose(res_sin, 2.0, abs_tol=1e-8)


def test_integration_validation() -> None:
    """Verify integration boundary error conditions."""
    with pytest.raises(ValueError, match="cannot exceed upper bound"):
        integrate_trapezoidal(lambda x: x, 2.0, 1.0, 10)
        
    with pytest.raises(ValueError, match="must be positive"):
        integrate_simpson(lambda x: x, 0.0, 1.0, 0)
