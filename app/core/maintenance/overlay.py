"""BBD overlay design — IRC:81-1997 (Guidelines for Strengthening of Flexible
Road Pavements using Benkelman Beam Deflection Technique, First Revision).

Authoritative basis for every constant in this module
-----------------------------------------------------
* Temperature correction (cl. 6.5)
    D_corrected = D_measured + (35 − T) × 0.0065     mm
  applied per individual reading, where T is pavement temperature in °C.
  The flat 0.0065 mm/°C factor is the IRC:81-1997 (and 1981) per-degree
  rebound-deflection correction (Khanna & Justo). Standard reference
  temperature: 35 °C.

* Seasonal correction factor (cl. 6.6) — engineer-supplied multiplier.
  Range typically 0.5–2.0; ≥ 1.0 when readings are taken in the moist /
  post-monsoon condition (no further correction needed); < 1.0 for dry
  season to amplify to the worst (post-monsoon) state.

* Characteristic deflection (cl. 7.2):
    Dc = mean(D) + k × SD
  with k taken by **road category**, NOT subgrade type:
    k = 2.00   →  Major arterials  (NH, SH, Expressway, Urban Arterial)
    k = 1.00   →  Other roads (MDR, ODR, Village)
  This matches IRC:81-1997 cl. 7.2.

* Allowable rebound deflection vs cumulative traffic (Plate 1 / Annex-2).
  Tabulated values (mm) at standard MSA points:
      1    →  1.50
      5    →  1.10
     10    →  0.90
     30    →  0.65
     50    →  0.60
    100    →  0.50
  Implementation: linear interpolation in log(N) below; outside the table
  the nearest end-value is held.

* Overlay thickness in terms of Bituminous Macadam (BM equivalent),
  IRC:81 design-chart fit (cl. 8.2):
      h_BM = 550 × log10(Dc / D_allow)        mm   (Dc > D_allow)
            = 0                                mm   (Dc ≤ D_allow)
  Layer-equivalency conversion (BM → DBM, BC, GSB) per Table 6 of IRC:81
  is **NOT modelled** in this skeleton — engineer must apply Table 6
  equivalencies after the BM thickness is known.

NOT included (deferred):
  * Layer-equivalency table (BM ↔ DBM ↔ BC ↔ GSB) — IRC:81 Table 6.
  * Stretch-wise zoning of deflection data.
  * Fatigue / rutting mechanistic check (IITPAVE).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from ..code_refs import CodeRef

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:81-1997", "cl. 6.5", "Temperature correction (0.0065 mm/°C to 35 °C)"),
    CodeRef("IRC:81-1997", "cl. 6.6", "Seasonal correction factor"),
    CodeRef("IRC:81-1997", "cl. 7.2", "Characteristic deflection Dc = mean + k·SD"),
    CodeRef("IRC:81-1997", "cl. 8.2", "h_BM = 550 · log10(Dc / D_allow)"),
    CodeRef("IRC:81-1997", "Plate 1", "Allowable deflection vs MSA"),
    CodeRef("IRC:81-1997", "Table 6", "Layer-equivalency conversion (deferred)"),
    CodeRef("IRC:115",     "",        "FWD-based evaluation (alternative method)"),
)


# ---------------------------------------------------------------------------
# Constants — IRC:81-1997
# ---------------------------------------------------------------------------

_T_REF_C = 35.0                    # reference pavement temperature
_T_CORR_PER_C = 0.0065             # mm/°C — IRC:81-1997 cl. 6.5

# k for Dc = mean + k·SD — IRC:81-1997 cl. 7.2
_K_MAJOR_ARTERIAL = 2.00
_K_OTHER_ROAD     = 1.00

_MAJOR_ARTERIAL_CATEGORIES = (
    "nh / sh", "nh", "sh", "expressway", "urban arterial",
)

# Allowable rebound deflection vs traffic — IRC:81-1997 Plate 1 (mm)
_ALLOWABLE_DEFLECTION_TABLE: Tuple[Tuple[float, float], ...] = (
    (1.0,   1.50),
    (5.0,   1.10),
    (10.0,  0.90),
    (30.0,  0.65),
    (50.0,  0.60),
    (100.0, 0.50),
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OverlayInput:
    deflections_mm: Tuple[float, ...] = ()        # individual rebound readings (mm)
    pavement_temp_c: float = 35.0                 # measured pavement temperature
    bituminous_thickness_mm: float = 100.0        # existing BC layer thickness (mm) — informational
    season_factor: float = 1.0                    # IRC:81 cl. 6.6 seasonal correction
    subgrade_type: str = "granular"               # kept for backward compatibility (not used in Dc)
    design_traffic_msa: float = 10.0              # cumulative design traffic (MSA)
    road_category: str = "NH / SH"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class OverlayResult:
    inputs: OverlayInput
    n_readings: int
    mean_deflection_mm: float
    stdev_deflection_mm: float
    characteristic_deflection_mm: float
    allowable_deflection_mm: float
    overlay_thickness_mm: float
    overlay_required: bool
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers — public for reuse / unit tests / report
# ---------------------------------------------------------------------------

def temperature_corrected_deflection(
    d_mm: float, pavement_temp_c: float, bc_thickness_mm: float | None = None
) -> float:
    """IRC:81-1997 cl. 6.5 — flat 0.0065 mm/°C correction to 35 °C reference.

    ``bc_thickness_mm`` is accepted for API compatibility but is not used in
    the standard IRC:81 per-reading correction (it is informational only).
    """
    return d_mm + (_T_REF_C - pavement_temp_c) * _T_CORR_PER_C


def _k_for_road_category(road_category: str) -> float:
    return (
        _K_MAJOR_ARTERIAL
        if road_category.strip().lower() in _MAJOR_ARTERIAL_CATEGORIES
        else _K_OTHER_ROAD
    )


def characteristic_deflection(
    corrected_readings: Tuple[float, ...], road_category: str = "NH / SH"
) -> Tuple[float, float, float]:
    """Return (mean, sample-stdev, Dc) given temperature-corrected readings.

    Dc per IRC:81-1997 cl. 7.2:
        Dc = mean + k · SD
        k = 2.0 for NH / SH / Expressway / Urban Arterial; k = 1.0 otherwise.
    """
    n = len(corrected_readings)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(corrected_readings) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in corrected_readings) / (n - 1)
        sd = math.sqrt(var)
    else:
        sd = 0.0
    dc = mean + _k_for_road_category(road_category) * sd
    return mean, sd, dc


def allowable_deflection(design_traffic_msa: float) -> float:
    """Allowable rebound deflection (mm) for given cumulative MSA.

    IRC:81-1997 Plate 1 — log-linear interpolation between the tabulated
    points; values held at the end-points outside the table range
    [1 MSA, 100 MSA].
    """
    if design_traffic_msa <= 0:
        return _ALLOWABLE_DEFLECTION_TABLE[0][1]
    if design_traffic_msa <= _ALLOWABLE_DEFLECTION_TABLE[0][0]:
        return _ALLOWABLE_DEFLECTION_TABLE[0][1]
    if design_traffic_msa >= _ALLOWABLE_DEFLECTION_TABLE[-1][0]:
        return _ALLOWABLE_DEFLECTION_TABLE[-1][1]

    log_n = math.log10(design_traffic_msa)
    for (n1, d1), (n2, d2) in zip(
        _ALLOWABLE_DEFLECTION_TABLE, _ALLOWABLE_DEFLECTION_TABLE[1:]
    ):
        if n1 <= design_traffic_msa <= n2:
            ln1, ln2 = math.log10(n1), math.log10(n2)
            t = (log_n - ln1) / (ln2 - ln1)
            return d1 + t * (d2 - d1)
    # Shouldn't reach
    return _ALLOWABLE_DEFLECTION_TABLE[-1][1]


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def compute_overlay(inp: OverlayInput) -> OverlayResult:
    """Run the full IRC:81-1997 BBD overlay-design calculation."""
    if not inp.deflections_mm:
        return OverlayResult(
            inputs=inp,
            n_readings=0,
            mean_deflection_mm=0.0,
            stdev_deflection_mm=0.0,
            characteristic_deflection_mm=0.0,
            allowable_deflection_mm=allowable_deflection(inp.design_traffic_msa),
            overlay_thickness_mm=0.0,
            overlay_required=False,
            notes="No deflection readings supplied — provide at least one reading.",
        )

    # 1. Per-reading temperature correction (IRC:81 cl. 6.5)
    t_corrected = tuple(
        temperature_corrected_deflection(d, inp.pavement_temp_c)
        for d in inp.deflections_mm
    )
    # 2. Seasonal correction factor (IRC:81 cl. 6.6) — engineer-supplied multiplier.
    sf = inp.season_factor if inp.season_factor > 0 else 1.0
    corrected = tuple(d * sf for d in t_corrected)

    mean, sd, dc = characteristic_deflection(corrected, inp.road_category)
    d_allow = allowable_deflection(inp.design_traffic_msa)

    # 3. BM-equivalent overlay thickness (IRC:81 cl. 8.2 design-chart fit)
    if dc > d_allow > 0:
        h = 550.0 * math.log10(dc / d_allow)
        h = max(0.0, h)
        required = h > 0.0
    else:
        h = 0.0
        required = False

    k = _k_for_road_category(inp.road_category)
    notes = (
        f"Method: IRC:81-1997. T-correction 0.0065 mm/°C to 35 °C "
        f"(cl. 6.5). Season factor = {sf:.2f} (cl. 6.6). "
        f"Dc = mean + {k:.2f}·SD (cl. 7.2, '{inp.road_category}'). "
        f"D_allow from Plate 1 at {inp.design_traffic_msa:g} MSA. "
        "Overlay thickness in BM-equivalent (cl. 8.2). Apply IRC:81 Table 6 "
        "equivalencies to convert to DBM/BC/GSB courses."
    )
    return OverlayResult(
        inputs=inp,
        n_readings=len(inp.deflections_mm),
        mean_deflection_mm=mean,
        stdev_deflection_mm=sd,
        characteristic_deflection_mm=dc,
        allowable_deflection_mm=d_allow,
        overlay_thickness_mm=h,
        overlay_required=required,
        notes=notes,
    )
