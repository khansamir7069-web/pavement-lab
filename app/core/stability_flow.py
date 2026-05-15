"""Marshall stability and flow with height check + volume correction.

Note: Excel uses literal `3.14` (not math.pi). Reproduced exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

PI_EXCEL = 3.14


@dataclass(frozen=True, slots=True)
class StabilitySpecimen:
    bitumen_pct: float
    sample_id: str
    height_readings_mm: tuple[float, float, float]
    diameter_mm: float
    correction_factor: float
    measured_stability_kn: float
    flow_mm: float
    include_in_stab_avg: bool = True
    include_in_flow_avg: bool = True
    # When set, used as the per-specimen "Corrected Stability" instead of L×M.
    # Mirrors the case where the lab technician manually overrides the corrected
    # value (the source workbook does this at Pb=3.5%).
    corrected_stability_kn_override: float | None = None


@dataclass(frozen=True, slots=True)
class StabilityFlowInput:
    specimens: tuple[StabilitySpecimen, ...]


@dataclass(frozen=True, slots=True)
class SpecimenComputed:
    bitumen_pct: float
    sample_id: str
    avg_height_mm: float
    height_ok: bool
    avg_height_cm: float
    diameter_cm: float
    volume_cm3: float
    corrected_stability_kn: float
    flow_mm: float
    include_stab: bool
    include_flow: bool


@dataclass(frozen=True, slots=True)
class StabilityFlowGroupResult:
    bitumen_pct: float
    specimens: tuple[SpecimenComputed, ...]
    avg_stability_kn: float
    avg_flow_mm: float
    marshall_quotient: float


@dataclass(frozen=True, slots=True)
class StabilityFlowResult:
    groups: tuple[StabilityFlowGroupResult, ...]

    def stab_flow_by_pb(self, pb: float, tol: float = 1e-6) -> tuple[float, float, float]:
        for g in self.groups:
            if abs(g.bitumen_pct - pb) < tol:
                return g.avg_stability_kn, g.avg_flow_mm, g.marshall_quotient
        raise KeyError(f"No Stab/Flow group for Pb={pb}")


def _compute_one(s: StabilitySpecimen) -> SpecimenComputed:
    avg_h_mm = sum(s.height_readings_mm) / len(s.height_readings_mm)
    h_ok = 61.5 <= avg_h_mm <= 65.5
    h_cm = avg_h_mm / 10
    d_cm = s.diameter_mm / 10
    vol = (PI_EXCEL / 4) * (d_cm * d_cm) * h_cm
    if s.corrected_stability_kn_override is not None:
        corr = s.corrected_stability_kn_override
    else:
        corr = s.correction_factor * s.measured_stability_kn
    return SpecimenComputed(
        bitumen_pct=s.bitumen_pct,
        sample_id=s.sample_id,
        avg_height_mm=avg_h_mm,
        height_ok=h_ok,
        avg_height_cm=h_cm,
        diameter_cm=d_cm,
        volume_cm3=vol,
        corrected_stability_kn=corr,
        flow_mm=s.flow_mm,
        include_stab=s.include_in_stab_avg,
        include_flow=s.include_in_flow_avg,
    )


def compute_stability_flow(inp: StabilityFlowInput) -> StabilityFlowResult:
    # group by bitumen content (preserve first-seen order)
    order: list[float] = []
    groups: dict[float, list[StabilitySpecimen]] = {}
    for sp in inp.specimens:
        if sp.bitumen_pct not in groups:
            order.append(sp.bitumen_pct)
            groups[sp.bitumen_pct] = []
        groups[sp.bitumen_pct].append(sp)

    out: list[StabilityFlowGroupResult] = []
    for pb in order:
        computed = tuple(_compute_one(sp) for sp in groups[pb])
        stab_included = [c for c in computed if c.include_stab]
        flow_included = [c for c in computed if c.include_flow]
        avg_stab = (
            sum(c.corrected_stability_kn for c in stab_included) / len(stab_included)
            if stab_included else 0.0
        )
        avg_flow = (
            sum(c.flow_mm for c in flow_included) / len(flow_included)
            if flow_included else 0.0
        )
        mq = avg_stab / avg_flow if avg_flow else 0.0
        out.append(StabilityFlowGroupResult(
            bitumen_pct=pb,
            specimens=computed,
            avg_stability_kn=avg_stab,
            avg_flow_mm=avg_flow,
            marshall_quotient=mq,
        ))
    return StabilityFlowResult(groups=tuple(out))
