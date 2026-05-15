"""Micro-surfacing — Type II / III proportioning skeleton per IRC:SP:81.

IRC:SP:81 "Tentative Specifications for Slurry Seal and Microsurfacing"
(2008, revised 2014) specifies polymer-modified bitumen-emulsion based
microsurfacing mixes in three nominal-size types (I, II, III).

Skeleton scope (this module):
  * Compute mix proportions per 100 kg aggregate.
  * Range-check residual binder % and additive-water % against the
    IRC:SP:81 Type II / III windows.

NOT modelled (deferred — must be done in the lab per IRC:SP:81):
  * Sieve-gradation envelope check (Tables 1/2 of IRC:SP:81).
  * Wet-Track Abrasion Test (WTAT) — cohesion check (IRC:SP:81 cl. 5.6).
  * Loaded Wheel Test (LWT) — lateral displacement (IRC:SP:81 cl. 5.7).
  * Cohesion test (IRC:SP:81 cl. 5.5) for setting time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..code_refs import CodeRef

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:SP:81",  "Tables 1/2", "Type I/II/III gradation envelopes"),
    CodeRef("IRC:SP:81",  "cl. 5.5",    "Cohesion / setting-time test"),
    CodeRef("IRC:SP:81",  "cl. 5.6",    "Wet-Track Abrasion Test (WTAT)"),
    CodeRef("IRC:SP:81",  "cl. 5.7",    "Loaded Wheel Test (LWT)"),
    CodeRef("IRC:SP:101", "",           "Specifications for Micro Surfacing"),
    CodeRef("IRC:SP:53",  "",           "Polymer-modified bitumen guidelines"),
)


@dataclass(frozen=True, slots=True)
class MicroSurfacingInput:
    surfacing_type: str = "Type II"            # Type I | Type II | Type III
    aggregate_mass_kg: float = 100.0
    emulsion_pct: float = 13.0                 # polymer-modified emulsion % of aggregate
    emulsion_residue_pct: float = 62.0
    additive_water_pct: float = 8.0
    mineral_filler_pct: float = 1.5            # OPC %
    notes: str = ""


@dataclass(frozen=True, slots=True)
class MicroSurfacingComponent:
    name: str
    mass_kg: float
    pct_of_aggregate: float


@dataclass(frozen=True, slots=True)
class MicroSurfacingResult:
    inputs: MicroSurfacingInput
    components: Tuple[MicroSurfacingComponent, ...]
    residual_binder_pct: float
    total_water_demand_pct: float
    pass_check: bool
    pass_reasons: Tuple[str, ...] = ()
    spec_residual_binder_pct: Tuple[float, float] = (5.5, 10.5)
    spec_filler_pct: Tuple[float, float] = (0.5, 3.0)
    notes: str = ""


# IRC:SP:81 — residual asphalt content (% of dry aggregate)
# Type I covered for completeness; Type II / III are the production-paving
# grades referenced for micro-surfacing.
_LIMITS = {
    "Type I":   {"residual_binder": (6.5, 10.5), "additive_water": (5.0, 12.0),
                 "filler": (0.5, 3.0)},
    "Type II":  {"residual_binder": (5.5, 10.5), "additive_water": (5.0, 12.0),
                 "filler": (0.5, 3.0)},
    "Type III": {"residual_binder": (5.5, 10.5), "additive_water": (5.0, 12.0),
                 "filler": (0.5, 3.0)},
}


def compute_micro_surfacing(inp: MicroSurfacingInput) -> MicroSurfacingResult:
    a = max(0.0, inp.aggregate_mass_kg)
    em_pct = max(0.0, inp.emulsion_pct)
    res_pct = max(0.0, min(100.0, inp.emulsion_residue_pct))
    w_pct = max(0.0, inp.additive_water_pct)
    f_pct = max(0.0, inp.mineral_filler_pct)

    emulsion_mass = a * em_pct / 100.0
    filler_mass = a * f_pct / 100.0
    water_mass = a * w_pct / 100.0
    residual_binder = emulsion_mass * res_pct / 100.0
    residual_pct = (residual_binder / a * 100.0) if a > 0 else 0.0
    # Total water demand = added water + free water already in emulsion
    water_in_emulsion = emulsion_mass * (100.0 - res_pct) / 100.0
    total_water_pct = ((water_mass + water_in_emulsion) / a * 100.0) if a > 0 else 0.0

    components = (
        MicroSurfacingComponent("Aggregate",         a,             100.0),
        MicroSurfacingComponent("Mineral filler",    filler_mass,   f_pct),
        MicroSurfacingComponent("Polymer-modified bitumen emulsion",
                                                     emulsion_mass, em_pct),
        MicroSurfacingComponent("Additive water",    water_mass,    w_pct),
        MicroSurfacingComponent("(residual binder)", residual_binder, residual_pct),
    )

    limits = _LIMITS.get(inp.surfacing_type, _LIMITS["Type II"])
    rb_lo, rb_hi = limits["residual_binder"]
    aw_lo, aw_hi = limits["additive_water"]
    fl_lo, fl_hi = limits["filler"]

    reasons: list[str] = []
    if not (rb_lo <= residual_pct <= rb_hi):
        reasons.append(
            f"Residual binder {residual_pct:.2f}% outside IRC:SP:81 "
            f"{inp.surfacing_type} window {rb_lo}–{rb_hi}%."
        )
    if not (aw_lo <= w_pct <= aw_hi):
        reasons.append(
            f"Additive water {w_pct:.2f}% outside IRC:SP:81 "
            f"{inp.surfacing_type} window {aw_lo}–{aw_hi}%."
        )
    if not (fl_lo <= f_pct <= fl_hi):
        reasons.append(
            f"Mineral filler {f_pct:.2f}% outside IRC:SP:81 "
            f"window {fl_lo}–{fl_hi}%."
        )
    pass_ok = not reasons

    note = (
        "Skeleton per IRC:SP:81. Only residual-binder, additive-water and "
        "mineral-filler envelopes are checked here. Gradation (IRC:SP:81 "
        "Tables 1/2), WTAT, LWT, cohesion and setting-time tests must be "
        "performed in the lab and reported separately."
    )
    return MicroSurfacingResult(
        inputs=inp,
        components=components,
        residual_binder_pct=residual_pct,
        total_water_demand_pct=total_water_pct,
        pass_check=pass_ok,
        pass_reasons=tuple(reasons),
        spec_residual_binder_pct=(rb_lo, rb_hi),
        spec_filler_pct=(fl_lo, fl_hi),
        notes=note,
    )
