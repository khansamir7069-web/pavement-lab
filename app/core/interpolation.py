"""Linear interpolation matching the Excel/VBA Module67 bracketing logic."""
from __future__ import annotations

from typing import Sequence


def linear_interpolate(x0: float, x1: float, y0: float, y1: float, x: float) -> float:
    if x1 == x0:
        return (y0 + y1) / 2
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def bracket_interpolate(
    xs: Sequence[float],
    ys: Sequence[float],
    target: float,
    fallback_index: int = 2,
) -> float:
    """Find the consecutive pair (x_i, x_{i+1}) that brackets target and interpolate.

    Matches the VBA pattern: walk pairs in order, accept first bracket where
    either x_i <= target <= x_{i+1} or x_i >= target >= x_{i+1}. If none, return
    ys[fallback_index].
    """
    n = min(len(xs), len(ys))
    for i in range(n - 1):
        if (xs[i] <= target <= xs[i + 1]) or (xs[i] >= target >= xs[i + 1]):
            return linear_interpolate(xs[i], xs[i + 1], ys[i], ys[i + 1], target)
    return ys[fallback_index] if 0 <= fallback_index < n else ys[n // 2]


def closest_index(xs: Sequence[float], target: float) -> int:
    return min(range(len(xs)), key=lambda i: abs(xs[i] - target))
