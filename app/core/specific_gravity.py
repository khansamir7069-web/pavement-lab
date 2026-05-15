"""Specific gravity calculations per IS 2386-III, IS 1201-1220."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class CoarseAggSGInput:
    """Wire-basket method. Each list has one entry per test repetition."""
    a_sample_plus_container_water: Sequence[float]  # A
    b_container_in_water: Sequence[float]            # B
    c_ssd_in_air: Sequence[float]                    # C
    d_ovendry_in_air: Sequence[float]                # D


@dataclass(frozen=True, slots=True)
class FineAggSGInput:
    """Pycnometer method."""
    w1_empty: Sequence[float]
    w2_dry_sample: Sequence[float]
    w3_dry_sample_water: Sequence[float]
    w4_water_only: Sequence[float]


@dataclass(frozen=True, slots=True)
class BitumenSGInput:
    """Specific gravity bottle method."""
    a_empty: Sequence[float]
    b_water: Sequence[float]
    c_sample: Sequence[float]
    d_sample_water: Sequence[float]


@dataclass(frozen=True, slots=True)
class SpecificGravityResult:
    bulk_ovendry: tuple[float, ...]
    bulk_ssd: tuple[float, ...]
    apparent: tuple[float, ...]
    absorption_pct: tuple[float, ...]
    avg_bulk_ovendry: float
    avg_bulk_ssd: float
    avg_apparent: float
    avg_absorption_pct: float


def _avg(seq: Sequence[float]) -> float:
    vals = [v for v in seq if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def compute_coarse_sg(i: CoarseAggSGInput) -> SpecificGravityResult:
    n = min(
        len(i.a_sample_plus_container_water),
        len(i.b_container_in_water),
        len(i.c_ssd_in_air),
        len(i.d_ovendry_in_air),
    )
    f_list, g_list, h_list, abs_list = [], [], [], []
    for k in range(n):
        a = i.a_sample_plus_container_water[k]
        b = i.b_container_in_water[k]
        c = i.c_ssd_in_air[k]
        d = i.d_ovendry_in_air[k]
        e = a - b
        f = d / (c - e)
        g = c / (c - e)
        h = d / (d - e)
        ab = ((c - d) / d) * 100
        f_list.append(f); g_list.append(g); h_list.append(h); abs_list.append(ab)
    return SpecificGravityResult(
        bulk_ovendry=tuple(f_list),
        bulk_ssd=tuple(g_list),
        apparent=tuple(h_list),
        absorption_pct=tuple(abs_list),
        avg_bulk_ovendry=_avg(f_list),
        avg_bulk_ssd=_avg(g_list),
        avg_apparent=_avg(h_list),
        avg_absorption_pct=_avg(abs_list),
    )


def compute_fine_sg(i: FineAggSGInput) -> SpecificGravityResult:
    n = min(len(i.w1_empty), len(i.w2_dry_sample), len(i.w3_dry_sample_water), len(i.w4_water_only))
    sg_list = []
    for k in range(n):
        ws = i.w2_dry_sample[k] - i.w1_empty[k]
        ww = ws - (i.w3_dry_sample_water[k] - i.w4_water_only[k])
        sg_list.append(ws / ww if ww else 0.0)
    return SpecificGravityResult(
        bulk_ovendry=tuple(sg_list),
        bulk_ssd=tuple(sg_list),
        apparent=tuple(sg_list),
        absorption_pct=tuple([0.0] * n),
        avg_bulk_ovendry=_avg(sg_list),
        avg_bulk_ssd=_avg(sg_list),
        avg_apparent=_avg(sg_list),
        avg_absorption_pct=0.0,
    )


def compute_bitumen_sg(i: BitumenSGInput) -> float:
    n = min(len(i.a_empty), len(i.b_water), len(i.c_sample), len(i.d_sample_water))
    sg_list = []
    for k in range(n):
        a, b, c, d = i.a_empty[k], i.b_water[k], i.c_sample[k], i.d_sample_water[k]
        denom = (b - a) - (d - c)
        if denom == 0:
            continue
        sg_list.append((c - a) / denom)
    return _avg(sg_list)


def compute_bulk_sg_blend(blend_ratios: dict[str, float], bulk_sg: dict[str, float]) -> float:
    """Harmonic-mean style blend: (Σ p_i) / (Σ p_i / g_i).

    Matches Excel Sp.Gr.!J37: (p1+p2+p3+p4) / (p1/g1 + p2/g2 + p3/g3 + p4/g4)
    """
    names = [n for n in blend_ratios if n in bulk_sg and blend_ratios[n] != 0]
    if not names:
        return 0.0
    numerator = sum(blend_ratios[n] for n in names)
    denominator = sum(blend_ratios[n] / bulk_sg[n] for n in names if bulk_sg[n] != 0)
    return numerator / denominator if denominator else 0.0
