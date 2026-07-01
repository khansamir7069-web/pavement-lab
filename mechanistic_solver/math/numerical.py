"""Numerical safety and error validation utilities for solver execution.

All math computations use float64 (float) parameters and check for finiteness.
"""
from __future__ import annotations

import math
from mechanistic_solver.core.constants import NUMERICAL_PRECISION_LIMIT


def safe_divide(num: float, den: float, fallback: float = 0.0) -> float:
    """Safely divide num by den, returning fallback if denominator is near zero."""
    if is_near_zero(den):
        return float(fallback)
    return float(num) / float(den)


def is_near_zero(val: float, tol: float = NUMERICAL_PRECISION_LIMIT) -> bool:
    """Check if value is near zero within a given tolerance limit."""
    return abs(float(val)) < float(tol)


def clamp_value(val: float, min_val: float, max_val: float) -> float:
    """Clamp a numerical value between min_val and max_val inclusive."""
    return max(float(min_val), min(float(max_val), float(val)))


def relative_error(approx: float, true_val: float) -> float:
    """Calculate the relative error between an approximation and true value."""
    if is_near_zero(true_val):
        return abs(float(approx) - float(true_val))
    return abs(float(approx) - float(true_val)) / abs(float(true_val))


def absolute_error(approx: float, true_val: float) -> float:
    """Calculate the absolute error between an approximation and true value."""
    return abs(float(approx) - float(true_val))


def validate_finite_number(val: float, name: str = "value") -> None:
    """Confirm a number is a real, finite float64.

    Raises:
        ValueError: If value is nan or inf.
    """
    f_val = float(val)
    if math.isnan(f_val) or math.isinf(f_val):
        raise ValueError(f"Numerical validation failed: '{name}' must be a finite float64. Got: {val}.")


def ensure_float64(val: Any) -> float:
    """Ensure that the input value is cast and returned as float64."""
    return float(val)
