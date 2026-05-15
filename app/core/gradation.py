"""Aggregate gradation: per-sieve blended % passing vs MoRTH spec."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GradationInput:
    sieve_sizes_mm: tuple[float, ...]
    # name -> tuple of % passing per sieve (same length as sieve_sizes_mm)
    pass_pct: Mapping[str, tuple[float, ...]]
    # name -> blend ratio in [0, 1]; sum must be ~1.0
    blend_ratios: Mapping[str, float]
    spec_lower: tuple[float, ...]
    spec_upper: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class GradationResult:
    sieve_sizes_mm: tuple[float, ...]
    pass_pct: Mapping[str, tuple[float, ...]]        # raw input per aggregate
    blend_ratios: Mapping[str, float]                 # raw input
    contributions: Mapping[str, tuple[float, ...]]    # pass_pct × ratio
    combined_pass_pct: tuple[float, ...]
    mid_limit: tuple[float, ...]
    spec_lower: tuple[float, ...]
    spec_upper: tuple[float, ...]
    within_spec: tuple[bool, ...]
    blend_ratio_sum: float


def compute_gradation(gi: GradationInput) -> GradationResult:
    n = len(gi.sieve_sizes_mm)
    contributions: dict[str, tuple[float, ...]] = {}
    for name, pct_seq in gi.pass_pct.items():
        ratio = gi.blend_ratios.get(name, 0.0)
        contributions[name] = tuple(p * ratio for p in pct_seq)

    combined = tuple(
        sum(contributions[name][i] for name in contributions) for i in range(n)
    )
    mid = tuple((lo + hi) / 2 for lo, hi in zip(gi.spec_lower, gi.spec_upper))
    within = tuple(lo <= c <= hi for lo, hi, c in zip(gi.spec_lower, gi.spec_upper, combined))
    blend_sum = sum(gi.blend_ratios.values())

    return GradationResult(
        sieve_sizes_mm=gi.sieve_sizes_mm,
        pass_pct={k: tuple(v) for k, v in gi.pass_pct.items()},
        blend_ratios=dict(gi.blend_ratios),
        contributions=contributions,
        combined_pass_pct=combined,
        mid_limit=mid,
        spec_lower=gi.spec_lower,
        spec_upper=gi.spec_upper,
        within_spec=within,
        blend_ratio_sum=blend_sum,
    )
