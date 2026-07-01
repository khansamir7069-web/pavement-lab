"""Hankel Transform mathematical utilities placeholder.

Provides standard integration skeletons using Bessel functions. Not optimized for
multilayer production systems.
"""
from __future__ import annotations

import warnings
from typing import Callable

from mechanistic_solver.math.bessel import j0, j1
from mechanistic_solver.math.integration import integrate_adaptive_simpson


def hankel_transform_order0(
    func: Callable[[float], float],
    r: float,
    upper_limit: float = 100.0,
    tolerance: float = 1e-6
) -> float:
    """Evaluate Hankel Transform of order 0 at radius r.

    Integrates: func(m) * J0(m * r) * dm from 0 to upper_limit.
    """
    warnings.warn(
        "hankel_transform_order0 is a prototype foundation, not yet optimized "
        "for multilayer layered elastic boundary equations.",
        UserWarning
    )
    
    def integrand(m: float) -> float:
        return func(m) * j0(m * r)
        
    return integrate_adaptive_simpson(integrand, 0.0, upper_limit, tolerance)


def hankel_transform_order1(
    func: Callable[[float], float],
    r: float,
    upper_limit: float = 100.0,
    tolerance: float = 1e-6
) -> float:
    """Evaluate Hankel Transform of order 1 at radius r.

    Integrates: func(m) * J1(m * r) * dm from 0 to upper_limit.
    """
    warnings.warn(
        "hankel_transform_order1 is a prototype foundation, not yet optimized.",
        UserWarning
    )
    
    def integrand(m: float) -> float:
        return func(m) * j1(m * r)
        
    return integrate_adaptive_simpson(integrand, 0.0, upper_limit, tolerance)
