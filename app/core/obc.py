"""Optimum bitumen content (OBC) and properties at OBC."""
from __future__ import annotations

from dataclasses import dataclass

from .interpolation import bracket_interpolate, closest_index, linear_interpolate
from .marshall import MarshallSummary


TARGET_AIR_VOIDS_PCT = 4.0


@dataclass(frozen=True, slots=True)
class OBCResult:
    obc_pct: float
    target_air_voids_pct: float
    gmb_at_obc: float
    stability_at_obc_kn: float
    flow_at_obc_mm: float
    vma_at_obc_pct: float
    vfb_at_obc_pct: float
    air_voids_at_obc_pct: float
    gmm_at_obc: float
    method: str             # "interpolated" or "closest_fallback"


def compute_obc(summary: MarshallSummary, target_air_voids: float = TARGET_AIR_VOIDS_PCT) -> float:
    pbs = list(summary.pbs)
    avs = list(summary.air_voids)
    # Walk pairs in order, accept first bracket
    for i in range(len(pbs) - 1):
        if (avs[i] >= target_air_voids and avs[i + 1] <= target_air_voids) or \
           (avs[i] <= target_air_voids and avs[i + 1] >= target_air_voids):
            return linear_interpolate(avs[i], avs[i + 1], pbs[i], pbs[i + 1], target_air_voids)
    return pbs[closest_index(avs, target_air_voids)]


def properties_at_obc(summary: MarshallSummary, target_air_voids: float = TARGET_AIR_VOIDS_PCT) -> OBCResult:
    obc = compute_obc(summary, target_air_voids)
    pbs = list(summary.pbs)

    # whether we got a true interpolation or fell back
    method = "closest_fallback"
    for i in range(len(pbs) - 1):
        avs = list(summary.air_voids)
        if (avs[i] >= target_air_voids and avs[i + 1] <= target_air_voids) or \
           (avs[i] <= target_air_voids and avs[i + 1] >= target_air_voids):
            method = "interpolated"
            break

    gmb = bracket_interpolate(pbs, [r.gmb for r in summary.rows], obc)
    stab = bracket_interpolate(pbs, [r.stability_kn for r in summary.rows], obc)
    flow = bracket_interpolate(pbs, [r.flow_mm for r in summary.rows], obc)
    vma = bracket_interpolate(pbs, [r.vma_pct for r in summary.rows], obc)
    vfb = bracket_interpolate(pbs, [r.vfb_pct for r in summary.rows], obc)
    av = bracket_interpolate(pbs, [r.air_voids_pct for r in summary.rows], obc)
    gmm = bracket_interpolate(pbs, [r.gmm for r in summary.rows], obc)

    return OBCResult(
        obc_pct=obc,
        target_air_voids_pct=target_air_voids,
        gmb_at_obc=gmb,
        stability_at_obc_kn=stab,
        flow_at_obc_mm=flow,
        vma_at_obc_pct=vma,
        vfb_at_obc_pct=vfb,
        air_voids_at_obc_pct=av,
        gmm_at_obc=gmm,
        method=method,
    )
