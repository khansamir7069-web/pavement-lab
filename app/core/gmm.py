"""Gmm — Theoretical maximum specific gravity (Rice method) + Gse + per-Pb Gmm."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class GmmSampleRaw:
    a_empty_flask: float
    b_flask_plus_dry_sample: float
    d_flask_filled_water: float
    e_flask_sample_water: float


@dataclass(frozen=True, slots=True)
class GmmInput:
    """Reference Pb (e.g. 4.5%) Rice test, plus list of design bitumen contents."""
    reference_pb_pct: float
    samples_at_reference: tuple[GmmSampleRaw, ...]
    design_pb_pct: tuple[float, ...]
    bitumen_sg: float                  # Gb (from Sp.Gr.)


@dataclass(frozen=True, slots=True)
class GmmResult:
    gmm_per_sample_at_ref: tuple[float, ...]
    gmm_avg_at_ref: float
    gse: float                          # effective SG of aggregate
    gmm_per_design_pb: tuple[tuple[float, float], ...]   # (Pb, Gmm)

    def gmm_by_pb(self, pb: float, tol: float = 1e-6) -> float:
        for p, g in self.gmm_per_design_pb:
            if abs(p - pb) < tol:
                return g
        raise KeyError(f"No Gmm for Pb={pb}")


def _rice_gmm(s: GmmSampleRaw) -> float:
    c = s.b_flask_plus_dry_sample - s.a_empty_flask
    denom = c + s.d_flask_filled_water - s.e_flask_sample_water
    return c / denom if denom else 0.0


def compute_gmm(inp: GmmInput) -> GmmResult:
    per_sample = tuple(_rice_gmm(s) for s in inp.samples_at_reference)
    gmm_avg = sum(per_sample) / len(per_sample) if per_sample else 0.0

    pb_ref = inp.reference_pb_pct
    gb = inp.bitumen_sg

    if gmm_avg == 0 or gb == 0:
        gse = 0.0
    else:
        # Gse = (100 - Pb_ref) / (100/Gmm_avg - Pb_ref/Gb)
        gse = (100.0 - pb_ref) / (100.0 / gmm_avg - pb_ref / gb)

    rows: list[tuple[float, float]] = []
    for pb in inp.design_pb_pct:
        ps = 100.0 - pb
        if gse == 0 or gb == 0:
            rows.append((pb, 0.0))
            continue
        gmm_pb = 100.0 / (ps / gse + pb / gb)
        rows.append((pb, gmm_pb))

    return GmmResult(
        gmm_per_sample_at_ref=per_sample,
        gmm_avg_at_ref=gmm_avg,
        gse=gse,
        gmm_per_design_pb=tuple(rows),
    )
