"""Gmb — Bulk specific gravity of compacted specimens with 95% CI check."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import stdev
from typing import Sequence


@dataclass(frozen=True, slots=True)
class GmbSpecimen:
    a_dry_in_air: float       # A
    c_in_water: float         # C (named D in some references)
    b_ssd_in_air: float       # B
    include: bool = True


@dataclass(frozen=True, slots=True)
class GmbGroup:
    """3 specimens for one bitumen content."""
    bitumen_pct: float
    specimens: tuple[GmbSpecimen, ...]


@dataclass(frozen=True, slots=True)
class GmbInput:
    groups: tuple[GmbGroup, ...]


@dataclass(frozen=True, slots=True)
class GmbGroupResult:
    bitumen_pct: float
    gmb_per_specimen: tuple[float, ...]
    mean: float
    stdev_sample: float
    ci_lower_95: float
    ci_upper_95: float
    acceptance: str           # "PASS" or "MORE SAMPLE REQUIRED"


@dataclass(frozen=True, slots=True)
class GmbResult:
    groups: tuple[GmbGroupResult, ...]

    def gmb_by_pb(self, pb: float, tol: float = 1e-6) -> float:
        for g in self.groups:
            if abs(g.bitumen_pct - pb) < tol:
                return g.mean
        raise KeyError(f"No Gmb group for Pb={pb}")


def _gmb(s: GmbSpecimen) -> float:
    denom = s.b_ssd_in_air - s.c_in_water
    return s.a_dry_in_air / denom if denom else 0.0


def compute_gmb(inp: GmbInput) -> GmbResult:
    out: list[GmbGroupResult] = []
    for group in inp.groups:
        values = tuple(_gmb(sp) for sp in group.specimens)
        included = [v for v, sp in zip(values, group.specimens) if sp.include]
        if not included:
            out.append(GmbGroupResult(
                bitumen_pct=group.bitumen_pct,
                gmb_per_specimen=values,
                mean=0.0, stdev_sample=0.0, ci_lower_95=0.0, ci_upper_95=0.0,
                acceptance="MORE SAMPLE REQUIRED",
            ))
            continue
        mean = sum(included) / len(included)
        sd = stdev(included) if len(included) > 1 else 0.0
        ll = mean - 1.96 * sd
        ul = mean + 1.96 * sd
        in_ci = all(ll <= v <= ul for v in included)
        out.append(GmbGroupResult(
            bitumen_pct=group.bitumen_pct,
            gmb_per_specimen=values,
            mean=mean,
            stdev_sample=sd,
            ci_lower_95=ll,
            ci_upper_95=ul,
            acceptance="PASS" if in_ci else "MORE SAMPLE REQUIRED",
        ))
    return GmbResult(groups=tuple(out))
