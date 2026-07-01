"""Bessel function evaluation library.

Uses scipy.special if available, otherwise employs stable series expansions
and asymptotic fallbacks.
"""
from __future__ import annotations

import math
import warnings

try:
    from scipy.special import j0 as scipy_j0, j1 as scipy_j1, jv as scipy_jv
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def j0(x: float) -> float:
    """Evaluate Bessel function of first kind, order 0 (J0)."""
    f_x = float(x)
    from mechanistic_solver.core.cache import global_cache
    cached = global_cache.get("bessel_j0", f_x)
    if cached is not None:
        return cached
        
    if _HAS_SCIPY:
        res = float(scipy_j0(f_x))
    else:
        # Stable fallback
        warnings.warn("SciPy not found. Using fallback series/asymptotic J0 approximation.", RuntimeWarning)
        abs_x = abs(f_x)
        if abs_x < 10.0:
            # Taylor series approximation
            term = 1.0
            sum_val = 1.0
            x2_4 = (f_x * f_x) / 4.0
            for k in range(1, 20):
                term *= -x2_4 / (k * k)
                sum_val += term
                if abs(term) < 1e-15:
                    break
            res = sum_val
        else:
            # Asymptotic approximation
            res = math.sqrt(2.0 / (math.pi * abs_x)) * math.cos(abs_x - math.pi / 4.0)
            
    global_cache.set("bessel_j0", f_x, res)
    return res


def j1(x: float) -> float:
    """Evaluate Bessel function of first kind, order 1 (J1)."""
    f_x = float(x)
    from mechanistic_solver.core.cache import global_cache
    cached = global_cache.get("bessel_j1", f_x)
    if cached is not None:
        return cached
        
    if _HAS_SCIPY:
        res = float(scipy_j1(f_x))
    else:
        # Stable fallback
        warnings.warn("SciPy not found. Using fallback series/asymptotic J1 approximation.", RuntimeWarning)
        abs_x = abs(f_x)
        if abs_x < 10.0:
            # Taylor series approximation
            term = f_x / 2.0
            sum_val = term
            x2_4 = (f_x * f_x) / 4.0
            for k in range(1, 20):
                term *= -x2_4 / (k * (k + 1))
                sum_val += term
                if abs(term) < 1e-15:
                    break
            res = sum_val
        else:
            # Asymptotic approximation
            sign = -1.0 if f_x < 0 else 1.0
            res = sign * math.sqrt(2.0 / (math.pi * abs_x)) * math.cos(abs_x - 3.0 * math.pi / 4.0)
            
    global_cache.set("bessel_j1", f_x, res)
    return res


def bessel_j(order: int, x: float) -> float:
    """Evaluate Bessel J of integer order at x."""
    f_x = float(x)
    if _HAS_SCIPY:
        return float(scipy_jv(order, f_x))
        
    if order == 0:
        return j0(f_x)
    elif order == 1:
        return j1(f_x)
    else:
        raise ValueError(f"Fallback Bessel only supports order 0 and 1. Requested: {order}.")
