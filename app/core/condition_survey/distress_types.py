"""Distress-type registry, severity levels, and PCI deduct weights.

ALL WEIGHTS ARE PLACEHOLDERS. The shape mirrors ASTM D6433 (deduct-value
method) but the numeric weights are uncalibrated — they must be tuned
against an empirical pavement-distress dataset in a later phase. The
``RECALIBRATE_ME`` flag is read by the engine and surfaced in every UI
banner and Word report so the engineer is told.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


RECALIBRATE_ME: bool = True

PLACEHOLDER_NOTE: str = (
    "PCI weights, severity multipliers and rehab recommendations in this "
    "module are PLACEHOLDER values pending calibration against an "
    "empirical distress dataset (ASTM D6433 deduct-value curves and the "
    "IRC:82 maintenance treatment matrix). Scores below are indicative "
    "only — confirm against the relevant clause before adoption."
)


# ---------------------------------------------------------------------------
# Severity levels — uniform low / medium / high scale
# ---------------------------------------------------------------------------

SEVERITY_LEVELS: Tuple[str, ...] = ("low", "medium", "high")

SEVERITY_WEIGHTS: Mapping[str, float] = {
    "low":    1.0,   # PLACEHOLDER
    "medium": 3.0,   # PLACEHOLDER
    "high":   6.0,   # PLACEHOLDER
}


# ---------------------------------------------------------------------------
# Distress type registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DistressType:
    code: str             # e.g. "cracking"
    label: str            # e.g. "Cracking"
    extent_unit: str      # "length_m" | "area_m2" | "count"
    weight: float         # base deduct weight — PLACEHOLDER
    note: str = ""


# Extent-unit aliases used by the engine
EXTENT_LENGTH = "length_m"
EXTENT_AREA   = "area_m2"
EXTENT_COUNT  = "count"


DISTRESS_TYPES: Mapping[str, DistressType] = {
    "cracking": DistressType(
        code="cracking", label="Cracking",
        extent_unit=EXTENT_LENGTH, weight=1.2,
        note="Includes longitudinal, transverse, alligator and block cracking "
             "(ASTM D6433). Extent recorded as total crack length in metres "
             "per 100 m segment.",
    ),
    "rutting": DistressType(
        code="rutting", label="Rutting",
        extent_unit=EXTENT_AREA, weight=1.5,
        note="Permanent deformation in wheel path. Extent recorded as the "
             "affected surface area in m^2 (severity reflects rut depth).",
    ),
    "potholes": DistressType(
        code="potholes", label="Potholes",
        extent_unit=EXTENT_COUNT, weight=2.0,
        note="Bowl-shaped holes through the surface course. Extent recorded "
             "as number of potholes (severity reflects diameter/depth band).",
    ),
    "ravelling": DistressType(
        code="ravelling", label="Ravelling",
        extent_unit=EXTENT_AREA, weight=0.9,
        note="Progressive loss of surface aggregate. Extent recorded as the "
             "affected surface area in m^2.",
    ),
    "bleeding": DistressType(
        code="bleeding", label="Bleeding",
        extent_unit=EXTENT_AREA, weight=0.7,
        note="Excess binder rising to the surface in warm weather. Extent "
             "recorded as the affected surface area in m^2.",
    ),
    "patch_failures": DistressType(
        code="patch_failures", label="Patch Failures",
        extent_unit=EXTENT_AREA, weight=1.1,
        note="Failure of a previously placed patch (cracking, rutting, "
             "settlement of the patch). Extent in m^2.",
    ),
}


# Extent-factor scaling — converts raw extent to a deduct-multiplier.
# PLACEHOLDER scaling, chosen so a 'medium' single-distress on a typical
# 100 m / 10 m^2 / 1-count unit lands the PCI around 90-95, and a 'high'
# extensive case crashes it past 50.

def extent_factor(distress_code: str, length_m: float, area_m2: float,
                  count: int) -> float:
    """Return the dimensionless extent factor for a distress record.

    PLACEHOLDER — divides the appropriate extent by a fixed reference
    (100 m / 10 m^2 / 1 count). Real ASTM D6433 uses log-curves; that
    calibration is deferred.
    """
    t = DISTRESS_TYPES.get(distress_code)
    if t is None:
        return 0.0
    if t.extent_unit == EXTENT_LENGTH:
        return max(0.0, length_m) / 100.0
    if t.extent_unit == EXTENT_AREA:
        return max(0.0, area_m2) / 10.0
    if t.extent_unit == EXTENT_COUNT:
        return float(max(0, count))
    return 0.0
