"""Pure-Python PCI engine + condition-survey dataclasses.

PCI = max(0, 100 - sum(deduct_values))
deduct_i = severity_weight[s] * distress_weight[t] * extent_factor(...)

ALL coefficients are PLACEHOLDERS (see distress_types.py). The engine
math itself is stable and mix-agnostic; only the constants need
calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from app.core.code_refs import CodeRef

from .distress_types import (
    DISTRESS_TYPES,
    PLACEHOLDER_NOTE,
    RECALIBRATE_ME,
    SEVERITY_LEVELS,
    SEVERITY_WEIGHTS,
    extent_factor,
    get_calibration,
)
from .rehab_recommendations import RehabRecommendation, recommend_rehab


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("ASTM-D6433", "",          "Pavement Condition Index — deduct-value method"),
    CodeRef("IRC:82-1982", "",         "Maintenance of Bituminous Surfaces"),
    CodeRef("IRC:81-1997", "",         "BBD-based overlay strengthening (rehab linkage)"),
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DistressRecord:
    distress_type: str          # one of DISTRESS_TYPES keys
    severity: str               # one of SEVERITY_LEVELS
    length_m: float = 0.0       # used iff DISTRESS_TYPES[t].extent_unit == length_m
    area_m2: float = 0.0        # used iff DISTRESS_TYPES[t].extent_unit == area_m2
    count: int = 0              # used iff DISTRESS_TYPES[t].extent_unit == count
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ConditionSurveyInput:
    """Survey-level metadata + distress records.

    Reserved fields (image_paths / ai_classification_hint /
    gis_geometry_geojson) are accepted but NOT consumed by the engine —
    they are placeholders so the dataclass shape stays stable when
    later phases add image / AI / GIS support.
    """
    work_name: str = ""
    surveyed_by: str = ""
    survey_date: str = ""           # free-text "YYYY-MM-DD" — engine doesn't parse
    chainage_from_km: float = 0.0
    chainage_to_km: float = 0.0
    lane_id: str = ""
    records: Tuple[DistressRecord, ...] = ()
    notes: str = ""
    # ---- Reserved placeholders (no logic — future expansion) ----
    image_paths: Tuple[str, ...] = ()              # Phase 11+
    ai_classification_hint: str = ""               # Phase 11+
    gis_geometry_geojson: str = ""                 # Phase 12+


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PerDistressBreakdown:
    distress_type: str
    severity: str
    extent_value: float          # raw user extent (length / area / count) collapsed to one number
    extent_unit: str             # "length_m" | "area_m2" | "count"
    deduct_value: float
    recommendation: RehabRecommendation


@dataclass(frozen=True, slots=True)
class ConditionSurveyResult:
    inputs: ConditionSurveyInput
    pci_score: float
    condition_category: str
    total_deduct: float
    breakdown: Tuple[PerDistressBreakdown, ...]
    references: Tuple[CodeRef, ...] = REFERENCES
    is_placeholder: bool = True       # always True in Phase 10
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def condition_category(pci: float) -> str:
    """ASTM D6433-style bucketing — PLACEHOLDER thresholds."""
    if pci >= 85.0:
        return "Excellent"
    if pci >= 70.0:
        return "Good"
    if pci >= 55.0:
        return "Fair"
    if pci >= 40.0:
        return "Poor"
    return "Very Poor"


def _deduct_for_record(rec: DistressRecord) -> float:
    t = DISTRESS_TYPES.get(rec.distress_type)
    if t is None:
        return 0.0
    s_w = SEVERITY_WEIGHTS.get(rec.severity, 0.0)
    if s_w == 0.0:
        return 0.0
    ef = extent_factor(rec.distress_type, rec.length_m, rec.area_m2, rec.count)
    return s_w * t.weight * ef


def _extent_value_and_unit(rec: DistressRecord) -> tuple[float, str]:
    t = DISTRESS_TYPES.get(rec.distress_type)
    if t is None:
        return 0.0, ""
    if t.extent_unit == "length_m":
        return rec.length_m, "length_m"
    if t.extent_unit == "area_m2":
        return rec.area_m2, "area_m2"
    return float(rec.count), "count"


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def compute_condition_survey(inp: ConditionSurveyInput) -> ConditionSurveyResult:
    """Compute PCI score, category, per-distress breakdown and placeholder
    rehab recommendations for the supplied distress records.
    """
    rows: list[PerDistressBreakdown] = []
    total = 0.0
    for rec in inp.records:
        dv = _deduct_for_record(rec)
        total += dv
        ev, unit = _extent_value_and_unit(rec)
        rows.append(PerDistressBreakdown(
            distress_type=rec.distress_type,
            severity=rec.severity,
            extent_value=ev,
            extent_unit=unit,
            deduct_value=dv,
            recommendation=recommend_rehab(rec.distress_type, rec.severity),
        ))
    pci = max(0.0, 100.0 - total)
    cal = get_calibration()
    note = (
        f"Calibration: {cal.label}. " + PLACEHOLDER_NOTE
        if cal.is_placeholder else
        f"Calibration: {cal.label}."
    )
    return ConditionSurveyResult(
        inputs=inp,
        pci_score=round(pci, 2),
        condition_category=condition_category(pci),
        total_deduct=round(total, 2),
        breakdown=tuple(rows),
        is_placeholder=cal.is_placeholder,
        notes=note,
    )
