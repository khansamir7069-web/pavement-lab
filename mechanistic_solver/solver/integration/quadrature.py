"""Quadrature utilities for layered elastic integration path controls.

Includes adaptive upper-limit evaluation and oscillation checks.
"""
from __future__ import annotations

import math
from typing import Callable


def is_finite(val: float) -> bool:
    """Verify that a float value is valid and finite."""
    return not (math.isnan(val) or math.isinf(val))


def detect_oscillations(
    func: Callable[[float], float],
    limit: float,
    steps: int = 50
) -> bool:
    """Detect potential high frequency oscillations by tracking sign changes."""
    sign_changes = 0
    prev_val = func(1e-5)
    prev_sign = prev_val >= 0.0
    
    xs = [limit * (i / steps) for i in range(1, steps + 1)]
    for x in xs:
        val = func(x)
        if not is_finite(val):
            continue
        sign = val >= 0.0
        if sign != prev_sign:
            sign_changes += 1
            prev_sign = sign
            
    # If the function changes signs frequently (e.g. > 10% of steps), flag oscillations
    return sign_changes > (steps * 0.1)
