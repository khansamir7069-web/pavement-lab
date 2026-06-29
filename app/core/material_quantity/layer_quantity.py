"""Layer-wise material-quantity engine — Phase 7.

Source tagging (all defaults live here, NOT in the UI):
  * DBM / BC mix tonnage           → MoRTH-500 / IRC:111
  * Binder demand (% of mix)       → IRC:111 / IRC:SP:16
  * Prime coat spray rates         → MoRTH-500 cl. 502
  * Tack coat spray rates          → MoRTH-500 cl. 503
  * GSB / WMM granular tonnage     → MoRTH-400 cl. 401 / 406

Formulas (all per kilometre, per single lane unless noted):

    A   = length_m × width_m                          [m²]
    For bituminous / granular layers:
        T_layer  = A · (t/1000) · ρ · (1 + waste)     [tonnes]
    For bituminous layers, binder tonnage:
        T_binder = T_layer · Pb / 100                 [tonnes]
    For sprayed bituminous coats (prime / tack):
        T_binder = A · r_kg/m² / 1000                 [tonnes]
        (no aggregate tonnage, no Pb)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple

from ..code_refs import CodeRef


# ---------------------------------------------------------------------------
# Engine references (consumed by report layer; no UI imports here)
# ---------------------------------------------------------------------------

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("MoRTH-500", "cl. 502", "Prime coat spray rates"),
    CodeRef("MoRTH-500", "cl. 503", "Tack coat spray rates"),
    CodeRef("MoRTH-500", "Table 500-9/-10/-17/-18",
            "DBM / BC mix construction"),
    CodeRef("MoRTH-400", "cl. 401", "Granular Sub-Base (GSB)"),
    CodeRef("MoRTH-400", "cl. 406", "Wet Mix Macadam (WMM)"),
    CodeRef("IRC:111",   "",        "Dense-graded bituminous mix specs"),
    CodeRef("IRC:SP:16", "",        "Bituminous mix design lab manual"),
)


# Layer-type catalogue. ``category`` drives the formula path:
#   "bituminous_mix" → tonnage + Pb-based binder demand
#   "sprayed_coat"   → A · spray_rate (binder only)
#   "granular"       → tonnage only, no binder
LAYER_TYPES: Tuple[str, ...] = (
    "BC", "DBM", "BM",                       # bituminous mixes
    "Prime Coat", "Tack Coat",               # sprayed binder coats
    "WMM", "GSB",                            # granular
)

_LAYER_CATEGORY: Mapping[str, str] = {
    "BC":         "bituminous_mix",
    "DBM":        "bituminous_mix",
    "BM":         "bituminous_mix",
    "Prime Coat": "sprayed_coat",
    "Tack Coat":  "sprayed_coat",
    "WMM":        "granular",
    "GSB":        "granular",
}

# Compacted bulk densities (t/m³) — typical values from MoRTH/IRC practice.
DEFAULT_DENSITY: Mapping[str, float] = {
    "BC":  2.40, "DBM": 2.40, "BM":  2.30,
    "WMM": 2.20, "GSB": 2.10,
}

# Default binder % by mass of mix (engineer overrides via Pb input).
DEFAULT_BINDER_PCT: Mapping[str, float] = {
    "BC":  5.5,
    "DBM": 4.5,
    "BM":  3.5,
}

# Default spray rates (kg/m²) per MoRTH-500 cl. 502 / 503.
# Mid-range values; UI shows the full window in the BOQ note.
DEFAULT_SPRAY_RATE_KGM2: Mapping[str, float] = {
    "Prime Coat": 0.75,    # 0.6–0.9 kg/m² (cl. 502, granular surfaces)
    "Tack Coat":  0.25,    # 0.20–0.30 kg/m² (cl. 503, bituminous surface)
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LayerInput:
    """One row in the BOQ table."""
    layer_type: str                    # one of LAYER_TYPES
    length_m: float = 1000.0
    width_m: float = 3.5
    thickness_mm: float = 40.0         # informational for sprayed coats
    density_t_m3: float | None = None  # None → DEFAULT_DENSITY
    binder_pct: float | None = None    # None → DEFAULT_BINDER_PCT
    spray_rate_kgm2: float | None = None  # None → DEFAULT_SPRAY_RATE_KGM2
    waste_pct: float = 2.0
    notes: str = ""


@dataclass(frozen=True, slots=True)
class LayerResult:
    inputs: LayerInput
    category: str                      # bituminous_mix | sprayed_coat | granular
    area_m2: float
    layer_tonnage_t: float             # mix or aggregate tonnage (0 for sprayed)
    binder_tonnage_t: float            # 0 for granular
    code_refs: Tuple[CodeRef, ...] = ()
    compacted_volume_m3: float = 0.0
    loose_volume_m3: float = 0.0
    bitumen_tonnage_t: float = 0.0
    cement_tonnage_t: float = 0.0
    filler_tonnage_t: float = 0.0
    aggregate_tonnage_t: float = 0.0


@dataclass(frozen=True, slots=True)
class MaterialQuantityInput:
    project_id: int | None = None
    layers: Tuple[LayerInput, ...] = ()
    notes: str = ""
    road_length_m: float = 1000.0
    carriageway_width_m: float = 7.0
    shoulder_width_m: float = 1.5


@dataclass(frozen=True, slots=True)
class MaterialQuantityResult:
    inputs: MaterialQuantityInput
    layers: Tuple[LayerResult, ...]
    total_layer_tonnage_t: float
    total_binder_tonnage_t: float
    total_area_m2: float
    references: Tuple[CodeRef, ...] = REFERENCES
    notes: str = ""
    total_compacted_volume_m3: float = 0.0
    total_loose_volume_m3: float = 0.0
    total_cement_tonnage_t: float = 0.0
    total_filler_tonnage_t: float = 0.0
    total_aggregate_tonnage_t: float = 0.0


# ---------------------------------------------------------------------------
# Core compute
# ---------------------------------------------------------------------------

def _refs_for(layer_type: str) -> Tuple[CodeRef, ...]:
    if layer_type in ("BC", "DBM"):
        return (CodeRef("MoRTH-500", "Table 500-9/-10/-17/-18", layer_type),
                CodeRef("IRC:111"))
    if layer_type == "BM":
        return (CodeRef("MoRTH-500", "Table 500-7"), CodeRef("IRC:27"))
    if layer_type == "Prime Coat":
        return (CodeRef("MoRTH-500", "cl. 502"),)
    if layer_type == "Tack Coat":
        return (CodeRef("MoRTH-500", "cl. 503"),)
    if layer_type == "WMM":
        return (CodeRef("MoRTH-400", "cl. 406"),)
    if layer_type == "GSB":
        return (CodeRef("MoRTH-400", "cl. 401"),)
    return ()


def compute_layer(inp: LayerInput) -> LayerResult:
    layer = inp.layer_type
    category = _LAYER_CATEGORY.get(layer, "bituminous_mix")
    a = max(0.0, inp.length_m) * max(0.0, inp.width_m)
    waste = max(0.0, inp.waste_pct) / 100.0

    compacted_vol = 0.0
    loose_vol = 0.0
    bitumen_t = 0.0
    cement_t = 0.0
    filler_t = 0.0
    aggregate_t = 0.0
    t_layer = 0.0

    if category == "sprayed_coat":
        rate = (inp.spray_rate_kgm2
                if inp.spray_rate_kgm2 is not None
                else DEFAULT_SPRAY_RATE_KGM2.get(layer, 0.0))
        bitumen_t = a * rate / 1000.0
        return LayerResult(
            inputs=inp, category=category, area_m2=a,
            layer_tonnage_t=0.0, binder_tonnage_t=bitumen_t,
            code_refs=_refs_for(layer),
            compacted_volume_m3=0.0, loose_volume_m3=0.0,
            bitumen_tonnage_t=bitumen_t, cement_tonnage_t=0.0,
            filler_tonnage_t=0.0, aggregate_tonnage_t=0.0
        )

    rho = (inp.density_t_m3
           if inp.density_t_m3 is not None
           else DEFAULT_DENSITY.get(layer, 2.30))
    compacted_vol = a * (max(0.0, inp.thickness_mm) / 1000.0)
    t_layer = compacted_vol * rho * (1.0 + waste)

    # Loose volume factor mapping
    loose_factor = 1.20
    if layer in ("BC", "DBM", "BM"):
        loose_factor = 1.15
    elif layer == "GSB":
        loose_factor = 1.25
    
    loose_vol = compacted_vol * loose_factor

    # Constituent splits
    if layer in ("CTB", "CTS"):
        pc = 4.5 if layer == "CTB" else 3.0
        if inp.binder_pct is not None and inp.binder_pct > 0.0:
            pc = inp.binder_pct
        cement_t = t_layer * pc / 100.0
        aggregate_t = t_layer - cement_t
    elif category == "granular":
        aggregate_t = t_layer
    elif layer == "BC":
        pb = (inp.binder_pct
              if inp.binder_pct is not None
              else DEFAULT_BINDER_PCT.get(layer, 5.5))
        pf = 2.0  # mineral filler default 2.0%
        bitumen_t = t_layer * pb / 100.0
        filler_t = t_layer * pf / 100.0
        aggregate_t = t_layer - bitumen_t - filler_t
    elif layer in ("DBM", "BM"):
        pb = (inp.binder_pct
              if inp.binder_pct is not None
              else DEFAULT_BINDER_PCT.get(layer, 4.5))
        bitumen_t = t_layer * pb / 100.0
        aggregate_t = t_layer - bitumen_t

    return LayerResult(
        inputs=inp, category=category, area_m2=a,
        layer_tonnage_t=t_layer, binder_tonnage_t=bitumen_t,
        code_refs=_refs_for(layer),
        compacted_volume_m3=compacted_vol,
        loose_volume_m3=loose_vol,
        bitumen_tonnage_t=bitumen_t,
        cement_tonnage_t=cement_t,
        filler_tonnage_t=filler_t,
        aggregate_tonnage_t=aggregate_t
    )


def compute_material_quantity(
    inp: MaterialQuantityInput,
) -> MaterialQuantityResult:
    results = tuple(compute_layer(l) for l in inp.layers)
    return MaterialQuantityResult(
        inputs=inp,
        layers=results,
        total_layer_tonnage_t=sum(r.layer_tonnage_t for r in results),
        total_binder_tonnage_t=sum(r.binder_tonnage_t for r in results),
        total_area_m2=sum(r.area_m2 for r in results) if results else 0.0,
        total_compacted_volume_m3=sum(r.compacted_volume_m3 for r in results),
        total_loose_volume_m3=sum(r.loose_volume_m3 for r in results),
        total_cement_tonnage_t=sum(r.cement_tonnage_t for r in results),
        total_filler_tonnage_t=sum(r.filler_tonnage_t for r in results),
        total_aggregate_tonnage_t=sum(r.aggregate_tonnage_t for r in results),
        notes=("Quantities are estimates per IRC/MoRTH typical defaults. "
               "Finalise densities / spray rates per the approved Job Mix "
               "Formula and site-specific lab tests."),
    )
