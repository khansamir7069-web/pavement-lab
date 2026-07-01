"""Unit tests for the parity error metrics and tolerance checking functions."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.validation.parity_metrics import (
    absolute_error,
    relative_error,
    percent_error,
    rmse,
    mae,
    max_abs_error,
    within_tolerance,
)


def test_absolute_error() -> None:
    """Verify absolute error calculation and non-finite/None safety."""
    assert absolute_error(10.0, 8.0) == pytest.approx(2.0)
    assert absolute_error(8.0, 10.0) == pytest.approx(2.0)
    assert absolute_error(None, 8.0) is None
    assert absolute_error(10.0, None) is None
    assert absolute_error(float("inf"), 8.0) is None


def test_relative_error() -> None:
    """Verify relative error calculation, zero-division, and None safety."""
    assert relative_error(10.0, 8.0) == pytest.approx(0.25)
    assert relative_error(8.0, 10.0) == pytest.approx(0.2)
    assert relative_error(10.0, 0.0) is None  # Zero division safe path
    assert relative_error(None, 8.0) is None
    assert relative_error(10.0, None) is None
    assert relative_error(float("nan"), 8.0) is None


def test_percent_error() -> None:
    """Verify percent error calculation and None safety."""
    assert percent_error(10.0, 8.0) == pytest.approx(25.0)
    assert percent_error(None, 8.0) is None


def test_rmse() -> None:
    """Verify RMSE calculation handles valid values and ignores None safely."""
    actuals = [10.0, 12.0, None, 15.0]
    expecteds = [8.0, 12.0, 14.0, 16.0]
    
    # Valid indices: 0 (diff=2), 1 (diff=0), 3 (diff=1)
    # RMSE = sqrt((4 + 0 + 1) / 3) = sqrt(5/3) = 1.29099
    res = rmse(actuals, expecteds)
    assert res is not None
    assert res == pytest.approx(math.sqrt(5.0 / 3.0))
    
    with pytest.raises(ValueError, match="lengths must match"):
        rmse([1.0], [1.0, 2.0])


def test_mae() -> None:
    """Verify MAE calculation handles valid values and ignores None safely."""
    actuals = [10.0, 12.0, None, 15.0]
    expecteds = [8.0, 12.0, 14.0, 16.0]
    
    # Valid indices: 0 (diff=2), 1 (diff=0), 3 (diff=1)
    # MAE = (2 + 0 + 1) / 3 = 1.0
    res = mae(actuals, expecteds)
    assert res is not None
    assert res == pytest.approx(1.0)


def test_max_abs_error() -> None:
    """Verify max absolute error calculation handles valid values and ignores None safely."""
    actuals = [10.0, 12.0, None, 15.0]
    expecteds = [8.0, 12.0, 14.0, 16.0]
    
    # Valid indices: 0 (diff=2), 1 (diff=0), 3 (diff=1) -> max is 2.0
    res = max_abs_error(actuals, expecteds)
    assert res is not None
    assert res == pytest.approx(2.0)


def test_within_tolerance() -> None:
    """Verify tolerance check matches absolute and relative criteria correctly."""
    # Within absolute tolerance
    assert within_tolerance(10.05, 10.0, abs_tol=0.1, rel_tol=0.01) is True
    # Out of absolute tolerance, but within relative tolerance
    # abs_diff = 0.5 > 0.1. rel_diff = 0.5/10 = 0.05 <= 0.05
    assert within_tolerance(10.5, 10.0, abs_tol=0.1, rel_tol=0.05) is True
    # Out of both
    assert within_tolerance(11.0, 10.0, abs_tol=0.1, rel_tol=0.05) is False
    # None cases
    assert within_tolerance(None, 10.0, abs_tol=0.1, rel_tol=0.05) is False
