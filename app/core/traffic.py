"""Traffic / ESAL / VDF / MSA engine — Phase 8.

Independent traffic analysis. Reuses ``compute_design_traffic`` from the
Phase-4 structural module (already verified) so the MSA formula stays in
one place. Adds IRC:37-2018 VDF and LDF preset tables, traffic-category
classification, and AASHTO-1993 ESAL aliasing.

Reserved placeholders (no logic yet) so future expansion (axle-load
spectrum, weigh-in-motion records, traffic-survey import) can land
without breaking the dataclass shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple

from .code_refs import CodeRef
from .structural_design import StructuralInput, compute_design_traffic


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:37-2018", "cl. 4.6",  "Cumulative design traffic (MSA)"),
    CodeRef("IRC:37-2018", "Table 1",  "VDF presets — terrain × CVPD"),
    CodeRef("IRC:37-2018", "cl. 4.4",  "Lane Distribution Factor (LDF) presets"),
    CodeRef("IRC:37-2018", "Plates 1-4", "Traffic category vs MSA"),
    CodeRef("AASHTO-1993", "",         "ESAL convention (alias of MSA × 1e6)"),
    CodeRef("AASHTO-T307", "",         "Resilient modulus (subgrade input)"),
)


TERRAINS: Tuple[str, ...] = ("Plain", "Rolling", "Hilly")
LANE_CONFIGS: Tuple[str, ...] = (
    "Single lane",
    "Two-lane (intermediate)",
    "Two-lane carriageway",
    "Four-lane divided",
    "Six-lane divided",
)


# VDF presets — IRC:37-2018 Table 1 (typical / mid-range values). Engineer
# overrides via direct VDF input on the panel. Keys: (terrain, cvpd_bucket).
_VDF_PRESETS: Mapping[Tuple[str, str], float] = {
    ("Plain",   "0-150"):    1.7,
    ("Plain",   "150-1500"): 3.9,
    ("Plain",   ">1500"):    4.8,
    ("Rolling", "0-150"):    1.7,
    ("Rolling", "150-1500"): 3.9,
    ("Rolling", ">1500"):    5.1,
    ("Hilly",   "0-150"):    0.5,
    ("Hilly",   "150-1500"): 0.6,
    ("Hilly",   ">1500"):    1.5,
}


# LDF presets — IRC:37-2018 cl. 4.4 (typical values).
_LDF_PRESETS: Mapping[str, float] = {
    "Single lane":             1.00,
    "Two-lane (intermediate)": 0.75,
    "Two-lane carriageway":    0.50,
    "Four-lane divided":       0.45,
    "Six-lane divided":        0.40,
}


def _cvpd_bucket(cvpd: float) -> str:
    if cvpd <= 150:
        return "0-150"
    if cvpd <= 1500:
        return "150-1500"
    return ">1500"


def vdf_preset(terrain: str, cvpd: float) -> float:
    """IRC:37-2018 Table 1 — typical VDF for terrain × CVPD bucket."""
    return _VDF_PRESETS.get((terrain, _cvpd_bucket(cvpd)), 3.5)


def ldf_preset(lane_config: str) -> float:
    """IRC:37-2018 cl. 4.4 — typical LDF for lane configuration."""
    return _LDF_PRESETS.get(lane_config, 0.50)


def traffic_category(msa: float) -> str:
    """IRC:37-2018 traffic category vs cumulative MSA (Plate selection)."""
    if msa <  5:   return "Low (< 5 MSA)"
    if msa < 30:   return "Moderate (5–30 MSA)"
    if msa < 100:  return "Heavy (30–100 MSA)"
    return "Very Heavy (> 100 MSA)"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TrafficInput:
    initial_cvpd: float = 2000.0
    growth_rate_pct: float = 7.5
    design_life_years: int = 15
    terrain: str = "Plain"
    lane_config: str = "Two-lane carriageway"
    vdf: float | None = None            # None → use _VDF_PRESETS lookup
    ldf: float | None = None            # None → use _LDF_PRESETS lookup
    road_category: str = "NH / SH"
    notes: str = ""
    # ---- Reserved placeholders (no logic — future expansion) ----
    axle_spectrum_kn: Tuple[float, ...] = ()
    wim_records: Tuple[float, ...] = ()
    survey_source_file: str = ""


@dataclass(frozen=True, slots=True)
class TrafficResult:
    inputs: TrafficInput
    vdf_used: float
    ldf_used: float
    growth_factor: float
    design_msa: float
    aashto_esal: float                   # = design_msa × 1e6
    traffic_category: str
    references: Tuple[CodeRef, ...] = REFERENCES
    notes: str = ""


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def compute_traffic_analysis(inp: TrafficInput) -> TrafficResult:
    vdf = inp.vdf if inp.vdf is not None else vdf_preset(inp.terrain, inp.initial_cvpd)
    ldf = inp.ldf if inp.ldf is not None else ldf_preset(inp.lane_config)
    # Delegate the IRC:37 cl. 4.6 formula to the verified structural engine
    s_in = StructuralInput(
        road_category=inp.road_category,
        design_life_years=inp.design_life_years,
        initial_cvpd=inp.initial_cvpd,
        growth_rate_pct=inp.growth_rate_pct,
        vdf=vdf,
        ldf=ldf,
    )
    msa, gf = compute_design_traffic(s_in)
    category = traffic_category(msa)
    note = (
        "Cumulative MSA via IRC:37-2018 cl. 4.6. VDF/LDF from IRC:37 "
        "Table 1 / cl. 4.4 when not user-supplied. AASHTO ESAL = MSA × 10^6."
    )
    return TrafficResult(
        inputs=inp,
        vdf_used=vdf,
        ldf_used=ldf,
        growth_factor=gf,
        design_msa=msa,
        aashto_esal=msa * 1_000_000.0,
        traffic_category=category,
        notes=note,
    )
