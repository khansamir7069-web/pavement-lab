"""Treatment categories, recommendation dataclass and placeholder thresholds.

The Phase-12 synthesis layer outputs one ``TreatmentRecommendation`` per
applicable treatment category. Each threshold lives on a single
``RehabThresholds`` dataclass so a future calibration phase can swap them
in via :func:`set_thresholds` without touching engine / rules code (the
same pattern Phase 10 uses for ``PCICalibration``).

ALL DECISION THRESHOLDS HERE ARE PLACEHOLDERS — defensible category
shapes from IRC:82-1982 / IRC:81-1997 / IRC:115 / IRC:SP:81 / IRC:SP:101
but the numeric cut-offs need calibration against a project sample
before V1 release.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.core.code_refs import CodeRef


PLACEHOLDER_NOTE: str = (
    "Rehab recommendations and decision thresholds in this module are "
    "PLACEHOLDER values pending calibration against project samples. "
    "Treatment category shapes follow IRC:82-1982 / IRC:81-1997 / "
    "IRC:115 / IRC:SP:81 / IRC:SP:101 but the numeric cut-offs are "
    "indicative only — engineer confirmation required before adoption."
)


# ---------------------------------------------------------------------------
# Treatment categories — 8 canonical buckets
# ---------------------------------------------------------------------------

TC_ROUTINE_MAINTENANCE: str = "routine_maintenance"
TC_CRACK_SEALING:       str = "crack_sealing"
TC_POTHOLE_PATCHING:    str = "pothole_patching"
TC_SURFACE_TREATMENT:   str = "surface_treatment"
TC_SLURRY_SEAL:         str = "slurry_seal"
TC_MICRO_SURFACING:     str = "micro_surfacing"
TC_OVERLAY:             str = "overlay"
TC_RECONSTRUCTION:      str = "reconstruction"

TREATMENT_CATEGORIES: Tuple[str, ...] = (
    TC_ROUTINE_MAINTENANCE,
    TC_CRACK_SEALING,
    TC_POTHOLE_PATCHING,
    TC_SURFACE_TREATMENT,
    TC_SLURRY_SEAL,
    TC_MICRO_SURFACING,
    TC_OVERLAY,
    TC_RECONSTRUCTION,
)


CATEGORY_LABELS: dict[str, str] = {
    TC_ROUTINE_MAINTENANCE: "Routine maintenance",
    TC_CRACK_SEALING:       "Crack sealing",
    TC_POTHOLE_PATCHING:    "Pothole patching",
    TC_SURFACE_TREATMENT:   "Surface treatment (surface dressing / fog seal)",
    TC_SLURRY_SEAL:         "Slurry seal",
    TC_MICRO_SURFACING:     "Micro-surfacing",
    TC_OVERLAY:             "Overlay / strengthening (BBD)",
    TC_RECONSTRUCTION:      "Reconstruction (placeholder)",
}


# Next-module hint — string ids consumed by the UI layer later.
CATEGORY_NEXT_MODULE: dict[str, str] = {
    TC_ROUTINE_MAINTENANCE: "none",
    TC_CRACK_SEALING:       "none",
    TC_POTHOLE_PATCHING:    "none",
    TC_SURFACE_TREATMENT:   "none",
    TC_SLURRY_SEAL:         "maintenance.cold_mix",       # nearest module
    TC_MICRO_SURFACING:     "maintenance.micro_surfacing",
    TC_OVERLAY:             "maintenance.overlay",
    TC_RECONSTRUCTION:      "structural_design",
}


# Priority — 1 = urgent / safety, 5 = routine.
CATEGORY_PRIORITY: dict[str, int] = {
    TC_RECONSTRUCTION:      1,
    TC_POTHOLE_PATCHING:    1,
    TC_OVERLAY:             2,
    TC_CRACK_SEALING:       3,
    TC_SURFACE_TREATMENT:   3,
    TC_SLURRY_SEAL:         3,
    TC_MICRO_SURFACING:     3,
    TC_ROUTINE_MAINTENANCE: 5,
}


# ---------------------------------------------------------------------------
# TreatmentRecommendation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TreatmentRecommendation:
    """One recommendation emitted by the synthesis engine.

    The ``reason`` and ``triggers`` fields exist so the UI / report can
    render an explainable trail — *why* the recommendation fired, not just
    *that* it did.
    """
    category: str
    label: str
    reason: str
    triggers: Tuple[str, ...]
    priority: int
    references: Tuple[CodeRef, ...]
    next_module: str = "none"
    is_placeholder: bool = True


# ---------------------------------------------------------------------------
# Placeholder thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RehabThresholds:
    """Single source of truth for every numeric cut-off the rule set uses.

    A future calibration phase replaces the active ``RehabThresholds`` via
    :func:`set_thresholds` — rules and engine read through it so callers
    never need to be rewired.
    """
    # PCI buckets — same shape as ConditionSurveyResult.condition_category
    # but exposed numerically so rules can compare without string parsing.
    pci_excellent_min: float = 85.0
    pci_good_min:      float = 70.0
    pci_fair_min:      float = 55.0
    pci_poor_min:      float = 40.0
    # Traffic buckets in MSA (IRC:37-2018 plates) — PLACEHOLDER.
    msa_low_max: float = 5.0     # ≤ this → slurry-seal eligible
    msa_mid_max: float = 30.0    # in (low, mid] → micro-surfacing eligible
    # Distress thresholds.
    ravelling_area_m2_min: float = 50.0     # below this, fog-seal only
    bleeding_area_m2_min:  float = 50.0
    label: str = "placeholder-default"
    is_placeholder: bool = True


DEFAULT_THRESHOLDS: RehabThresholds = RehabThresholds()


_ACTIVE_THRESHOLDS: RehabThresholds = DEFAULT_THRESHOLDS


def get_thresholds() -> RehabThresholds:
    """Return the currently active threshold set."""
    return _ACTIVE_THRESHOLDS


def set_thresholds(t: RehabThresholds) -> RehabThresholds:
    """Install a new threshold set; returns the previous one."""
    global _ACTIVE_THRESHOLDS
    prev = _ACTIVE_THRESHOLDS
    _ACTIVE_THRESHOLDS = t
    return prev


def reset_thresholds() -> None:
    """Restore the placeholder default thresholds."""
    set_thresholds(DEFAULT_THRESHOLDS)


# ---------------------------------------------------------------------------
# Shared CodeRef constants — reused from the project's code_registry.json
# ---------------------------------------------------------------------------

CR_IRC82      = CodeRef("IRC:82-1982", "",          "Maintenance of Bituminous Surfaces")
CR_IRC82_52   = CodeRef("IRC:82-1982", "cl. 5.2",   "Surface dressing / seal coat")
CR_IRC82_53   = CodeRef("IRC:82-1982", "cl. 5.3",   "Crack sealing")
CR_IRC82_54   = CodeRef("IRC:82-1982", "cl. 5.4",   "Pothole patching")
CR_IRC81      = CodeRef("IRC:81-1997", "",          "BBD-based overlay strengthening")
CR_IRC115     = CodeRef("IRC:115",     "",          "Structural evaluation / strengthening using FWD")
CR_IRC19      = CodeRef("IRC:19",      "",          "Bituminous surface dressing")
CR_IRC_SP_81  = CodeRef("IRC:SP:81",   "",          "Slurry seal and microsurfacing")
CR_IRC_SP_101 = CodeRef("IRC:SP:101",  "",          "Micro-surfacing specification")
CR_MORTH_3004 = CodeRef("MoRTH-900",   "Sec. 3004", "Pothole patching specification")
