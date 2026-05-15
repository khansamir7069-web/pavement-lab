"""Cold bituminous mix — proportioning skeleton per IRC:SP:100-2014.

IRC:SP:100-2014 "Use of Cold Mix Technology in Construction and Maintenance
of Roads Using Bitumen Emulsion" recommends the Marshall method for
determining the Optimum Residual Asphalt Content (ORAC).

Skeleton scope (this module):
  * Compute residual binder from emulsion content × emulsion residue %.
  * Range-check the residual binder against IRC:SP:100 / common-practice
    windows split by gradation type (dense vs open).
  * Produce a per-100-kg-aggregate mix proportion table.

NOT modelled (deferred — must be done in the lab per IRC:SP:100):
  * Optimum Pre-Wetting Water Content (OPWC) determination.
  * Marshall stability / flow on cold-mix specimens.
  * Coating, stripping, water sensitivity (retained-stability) tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..code_refs import CodeRef

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:SP:100-2014", "cl. 7",   "Marshall-based mix design (ORAC)"),
    CodeRef("IRC:SP:100-2014", "cl. 7.3", "Optimum Pre-Wetting Water Content (OPWC)"),
    CodeRef("IRC:SP:98",       "",        "Earlier cold-mix technology guidelines"),
    CodeRef("MoRTH-500",       "",        "Bituminous construction reference"),
    CodeRef("ASTM-D6927",      "",        "Marshall stability & flow test method"),
)


@dataclass(frozen=True, slots=True)
class ColdMixInput:
    aggregate_mass_kg: float = 100.0           # basis: per 100 kg aggregate
    emulsion_pct: float = 8.0                  # emulsion % by mass of aggregate
    emulsion_residue_pct: float = 60.0         # bitumen residue % in emulsion (per supplier datasheet)
    water_addition_pct: float = 4.0            # extra water % by mass of aggregate (pre-wetting)
    filler_pct: float = 2.0                    # mineral filler % (e.g. OPC)
    mix_type: str = "Dense-Graded"             # Dense-Graded | Open-Graded
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ColdMixComponent:
    name: str
    mass_kg: float
    pct_of_aggregate: float


@dataclass(frozen=True, slots=True)
class ColdMixResult:
    inputs: ColdMixInput
    components: Tuple[ColdMixComponent, ...]
    residual_binder_pct: float       # % of aggregate mass
    total_mix_mass_kg: float
    pass_check: bool                 # True if residual binder inside the IRC:SP:100 window
    pass_reasons: Tuple[str, ...] = ()
    spec_window_pct: Tuple[float, float] = (3.0, 5.0)
    notes: str = ""


# IRC:SP:100-2014 — typical residual-binder ranges by gradation
# (% of dry aggregate mass). Final value must be fixed by Marshall in lab.
_RESIDUAL_BINDER_WINDOW: dict[str, Tuple[float, float]] = {
    "Dense-Graded": (3.0, 5.0),
    "Open-Graded":  (2.5, 4.5),
}


def compute_cold_mix(inp: ColdMixInput) -> ColdMixResult:
    a = max(0.0, inp.aggregate_mass_kg)
    em_pct = max(0.0, inp.emulsion_pct)
    res_pct = max(0.0, min(100.0, inp.emulsion_residue_pct))
    w_pct = max(0.0, inp.water_addition_pct)
    f_pct = max(0.0, inp.filler_pct)

    emulsion_mass = a * em_pct / 100.0
    filler_mass = a * f_pct / 100.0
    water_mass = a * w_pct / 100.0
    residual_binder = emulsion_mass * res_pct / 100.0
    residual_pct = (residual_binder / a * 100.0) if a > 0 else 0.0

    components = (
        ColdMixComponent("Aggregate",            a,             100.0),
        ColdMixComponent("Mineral filler",       filler_mass,   f_pct),
        ColdMixComponent("Bitumen emulsion",     emulsion_mass, em_pct),
        ColdMixComponent("Added (pre-wetting) water", water_mass, w_pct),
        ColdMixComponent("(residual binder)",    residual_binder, residual_pct),
    )
    total = a + filler_mass + emulsion_mass + water_mass

    window = _RESIDUAL_BINDER_WINDOW.get(inp.mix_type, _RESIDUAL_BINDER_WINDOW["Dense-Graded"])
    lo, hi = window
    reasons: list[str] = []
    if not (lo <= residual_pct <= hi):
        reasons.append(
            f"Residual binder {residual_pct:.2f}% outside the IRC:SP:100-2014 "
            f"{inp.mix_type} window {lo:.1f}–{hi:.1f}%."
        )
    pass_ok = not reasons

    note = (
        "Skeleton proportioning per IRC:SP:100-2014. Ranges shown are "
        "typical practice; finalise residual binder via Marshall test "
        "(IRC:SP:100 cl. 7) using the Optimum Pre-Wetting Water Content "
        "established on the supplied aggregate."
    )
    return ColdMixResult(
        inputs=inp,
        components=components,
        residual_binder_pct=residual_pct,
        total_mix_mass_kg=total,
        pass_check=pass_ok,
        pass_reasons=tuple(reasons),
        spec_window_pct=(lo, hi),
        notes=note,
    )
