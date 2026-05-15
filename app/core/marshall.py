"""Marshall mix-design summary: per-Pb Air Voids, VMA, VFB, MQ."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarshallRow:
    bitumen_pct: float
    aggregate_pct: float        # 100 - Pb
    gmm: float
    gmb: float
    air_voids_pct: float        # VIM
    vma_pct: float
    vfb_pct: float
    stability_kn: float
    flow_mm: float
    marshall_quotient: float


@dataclass(frozen=True, slots=True)
class MarshallSummary:
    rows: tuple[MarshallRow, ...]
    gsb: float                  # bulk SG of combined aggregate

    @property
    def pbs(self) -> tuple[float, ...]:
        return tuple(r.bitumen_pct for r in self.rows)

    @property
    def air_voids(self) -> tuple[float, ...]:
        return tuple(r.air_voids_pct for r in self.rows)


def build_marshall_summary(
    design_pb_pct: tuple[float, ...],
    gmm_by_pb: dict[float, float],
    gmb_by_pb: dict[float, float],
    stab_flow_by_pb: dict[float, tuple[float, float, float]],
    gsb: float,
) -> MarshallSummary:
    """Compose final summary table.

    Excel reference: Charts!A2:J6 — see CALCULATION_SPEC §3.9.
    """
    rows: list[MarshallRow] = []
    for pb in design_pb_pct:
        ps = 100.0 - pb
        gmm = gmm_by_pb[pb]
        gmb = gmb_by_pb[pb]
        air_voids = ((gmm - gmb) / gmm) * 100 if gmm else 0.0
        vma = 100.0 - ((gmb * ps) / gsb) if gsb else 0.0
        vfb = ((vma - air_voids) / vma) * 100 if vma else 0.0
        stab, flow, mq = stab_flow_by_pb[pb]
        rows.append(MarshallRow(
            bitumen_pct=pb,
            aggregate_pct=ps,
            gmm=gmm,
            gmb=gmb,
            air_voids_pct=air_voids,
            vma_pct=vma,
            vfb_pct=vfb,
            stability_kn=stab,
            flow_mm=flow,
            marshall_quotient=mq,
        ))
    return MarshallSummary(rows=tuple(rows), gsb=gsb)
