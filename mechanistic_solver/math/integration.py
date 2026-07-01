"""Numerical integration quadrature utilities for pavement calculations.

Enforces parameter bounds and finite function evaluation outputs.
"""
from __future__ import annotations

import math
from typing import Callable
from mechanistic_solver.math.numerical import validate_finite_number


def integrate_trapezoidal(func: Callable[[float], float], a: float, b: float, n: int) -> float:
    """Numerical integration using the composite Trapezoidal Rule.

    Args:
        func: Integrand function.
        a: Lower integration bound.
        b: Upper integration bound.
        n: Number of intervals.

    Returns:
        float: Computed integral value.
    """
    if n <= 0:
        raise ValueError(f"Number of intervals 'n' must be positive. Got: {n}.")
    if b < a:
        raise ValueError(f"Lower bound 'a' ({a}) cannot exceed upper bound 'b' ({b}).")
        
    if math.isclose(a, b):
        return 0.0
        
    h = (b - a) / n
    fa = func(a)
    fb = func(b)
    validate_finite_number(fa, "f(a)")
    validate_finite_number(fb, "f(b)")
    
    total = 0.5 * (fa + fb)
    for i in range(1, n):
        fx = func(a + i * h)
        validate_finite_number(fx, f"f(x_{i})")
        total += fx
        
    return total * h


def integrate_simpson(func: Callable[[float], float], a: float, b: float, n: int) -> float:
    """Numerical integration using composite Simpson's 1/3 Rule.

    Args:
        func: Integrand function.
        a: Lower bound.
        b: Upper bound.
        n: Number of intervals (must be even).

    Returns:
        float: Computed integral value.
    """
    if n <= 0:
        raise ValueError(f"Number of intervals 'n' must be positive. Got: {n}.")
    if n % 2 != 0:
        raise ValueError(f"Simpson's rule requires an even number of intervals. Got: {n}.")
    if b < a:
        raise ValueError(f"Lower bound 'a' ({a}) cannot exceed upper bound 'b' ({b}).")
        
    if math.isclose(a, b):
        return 0.0
        
    h = (b - a) / n
    fa = func(a)
    fb = func(b)
    validate_finite_number(fa, "f(a)")
    validate_finite_number(fb, "f(b)")
    
    total = fa + fb
    for i in range(1, n):
        fx = func(a + i * h)
        validate_finite_number(fx, f"f(x_{i})")
        if i % 2 == 1:
            total += 4.0 * fx
        else:
            total += 2.0 * fx
            
    return total * (h / 3.0)


def integrate_adaptive_simpson(
    func: Callable[[float], float],
    a: float,
    b: float,
    tolerance: float = 1e-6,
    max_depth: int = 15
) -> float:
    """Adaptive Simpson's quadrature routine.

    Args:
        func: Integrand function.
        a: Lower bound.
        b: Upper bound.
        tolerance: Absolute error target limit.
        max_depth: Maximum recursion depth.

    Returns:
        float: Computed integral value.
    """
    if b < a:
        raise ValueError(f"Lower bound 'a' ({a}) cannot exceed upper bound 'b' ({b}).")
    if tolerance <= 0.0:
        raise ValueError(f"Tolerance must be positive. Got: {tolerance}.")
        
    if math.isclose(a, b):
        return 0.0
        
    fa = func(a)
    fb = func(b)
    validate_finite_number(fa, "f(a)")
    validate_finite_number(fb, "f(b)")
    
    m = (a + b) / 2.0
    fm = func(m)
    validate_finite_number(fm, "f(mid)")
    
    whole = (b - a) / 6.0 * (fa + 4.0 * fm + fb)
    
    return _adaptive_simpson_recursive(func, a, b, tolerance, whole, fa, fb, fm, 0, max_depth)


def _adaptive_simpson_recursive(
    func: Callable[[float], float],
    a: float,
    b: float,
    tol: float,
    whole: float,
    fa: float,
    fb: float,
    fm: float,
    depth: int,
    max_depth: int
) -> float:
    m = (a + b) / 2.0
    lm = (a + m) / 2.0
    rm = (m + b) / 2.0
    
    flm = func(lm)
    frm = func(rm)
    validate_finite_number(flm, "f(left_mid)")
    validate_finite_number(frm, "f(right_mid)")
    
    left = (m - a) / 6.0 * (fa + 4.0 * flm + fm)
    right = (b - m) / 6.0 * (fm + 4.0 * frm + fb)
    
    delta = left + right - whole
    if depth >= max_depth or abs(delta) <= 15.0 * tol:
        return left + right + delta / 15.0
        
    next_tol = tol / 2.0
    left_integral = _adaptive_simpson_recursive(
        func, a, m, next_tol, left, fa, fm, flm, depth + 1, max_depth
    )
    right_integral = _adaptive_simpson_recursive(
        func, m, b, next_tol, right, fm, fb, frm, depth + 1, max_depth
    )
    
    return left_integral + right_integral
