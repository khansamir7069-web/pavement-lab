"""Parity metrics calculations checking errors between RoadX and IITPAVE."""
from __future__ import annotations

import math
from typing import Sequence


def absolute_error(a: float | None, b: float | None) -> float | None:
    """Calculate absolute error |a - b| handling None and non-finite values."""
    if a is None or b is None:
        return None
    if not math.isfinite(a) or not math.isfinite(b):
        return None
    return abs(a - b)


def relative_error(a: float | None, b: float | None) -> float | None:
    """Calculate relative error |a - b| / |b| handling zero divisions, None, and non-finite values."""
    if a is None or b is None:
        return None
    if not math.isfinite(a) or not math.isfinite(b):
        return None
    if abs(b) < 1e-15:
        return None
    return abs(a - b) / abs(b)


def percent_error(a: float | None, b: float | None) -> float | None:
    """Calculate percent error handling None and non-finite values."""
    rel = relative_error(a, b)
    if rel is None:
        return None
    return rel * 100.0


def rmse(actuals: Sequence[float | None], expecteds: Sequence[float | None]) -> float | None:
    """Calculate Root Mean Square Error (RMSE) skipping invalid/missing cases."""
    if len(actuals) != len(expecteds):
        raise ValueError("Sequence lengths must match for RMSE calculation.")
    
    sq_diffs = []
    for act, exp in zip(actuals, expecteds):
        if act is not None and exp is not None and math.isfinite(act) and math.isfinite(exp):
            sq_diffs.append((act - exp) ** 2)
            
    if not sq_diffs:
        return None
    return math.sqrt(sum(sq_diffs) / len(sq_diffs))


def mae(actuals: Sequence[float | None], expecteds: Sequence[float | None]) -> float | None:
    """Calculate Mean Absolute Error (MAE) skipping invalid/missing cases."""
    if len(actuals) != len(expecteds):
        raise ValueError("Sequence lengths must match for MAE calculation.")
    
    abs_diffs = []
    for act, exp in zip(actuals, expecteds):
        if act is not None and exp is not None and math.isfinite(act) and math.isfinite(exp):
            abs_diffs.append(abs(act - exp))
            
    if not abs_diffs:
        return None
    return sum(abs_diffs) / len(abs_diffs)


def max_abs_error(actuals: Sequence[float | None], expecteds: Sequence[float | None]) -> float | None:
    """Calculate Maximum Absolute Error skipping invalid/missing cases."""
    if len(actuals) != len(expecteds):
        raise ValueError("Sequence lengths must match for Max Absolute Error.")
    
    abs_diffs = []
    for act, exp in zip(actuals, expecteds):
        if act is not None and exp is not None and math.isfinite(act) and math.isfinite(exp):
            abs_diffs.append(abs(act - exp))
            
    if not abs_diffs:
        return None
    return max(abs_diffs)


def within_tolerance(
    actual: float | None,
    expected: float | None,
    abs_tol: float,
    rel_tol: float
) -> bool:
    """Check if actual value falls within absolute or relative tolerances of expected."""
    if actual is None or expected is None:
        return False
    if not math.isfinite(actual) or not math.isfinite(expected):
        return False
    
    abs_err = abs(actual - expected)
    if abs_err <= abs_tol:
        return True
        
    if abs(expected) > 1e-15:
        rel_err = abs_err / abs(expected)
        if rel_err <= rel_tol:
            return True
            
    return False
