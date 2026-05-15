"""Phase-12 rehabilitation recommendation synthesis engine.

Sits *above* the row-level
``app.core.condition_survey.rehab_recommendations.recommend_rehab``:
that function maps a single (distress, severity) pair to one IRC:82
treatment, while this engine takes the survey-level outputs (PCI +
distress breakdown + optional traffic / maintenance designs) and emits a
prioritized, source-tagged list of project-level treatment
recommendations.

All decision thresholds are PLACEHOLDER and exposed via
``RehabThresholds`` so a future calibration phase can swap them through
:func:`set_thresholds` without touching engine / rules code.
"""
from __future__ import annotations

from .engine import (
    RecommendationContext,
    RehabSynthesisResult,
    REFERENCES,
    compute_rehab_recommendations,
)
from .rules import (
    DEFAULT_RULES,
    Rule,
    rule_crack_sealing,
    rule_micro_surfacing,
    rule_overlay,
    rule_pothole_patching,
    rule_reconstruction,
    rule_routine_maintenance,
    rule_slurry_seal,
    rule_surface_treatment,
)
from .treatments import (
    CATEGORY_LABELS,
    CATEGORY_NEXT_MODULE,
    CATEGORY_PRIORITY,
    DEFAULT_THRESHOLDS,
    PLACEHOLDER_NOTE,
    RehabThresholds,
    TC_CRACK_SEALING,
    TC_MICRO_SURFACING,
    TC_OVERLAY,
    TC_POTHOLE_PATCHING,
    TC_RECONSTRUCTION,
    TC_ROUTINE_MAINTENANCE,
    TC_SLURRY_SEAL,
    TC_SURFACE_TREATMENT,
    TREATMENT_CATEGORIES,
    TreatmentRecommendation,
    get_thresholds,
    reset_thresholds,
    set_thresholds,
)

__all__ = [
    # context + synthesis
    "RecommendationContext",
    "RehabSynthesisResult",
    "REFERENCES",
    "compute_rehab_recommendations",
    # rules
    "DEFAULT_RULES",
    "Rule",
    "rule_crack_sealing",
    "rule_micro_surfacing",
    "rule_overlay",
    "rule_pothole_patching",
    "rule_reconstruction",
    "rule_routine_maintenance",
    "rule_slurry_seal",
    "rule_surface_treatment",
    # treatments / thresholds
    "CATEGORY_LABELS",
    "CATEGORY_NEXT_MODULE",
    "CATEGORY_PRIORITY",
    "DEFAULT_THRESHOLDS",
    "PLACEHOLDER_NOTE",
    "RehabThresholds",
    "TC_CRACK_SEALING",
    "TC_MICRO_SURFACING",
    "TC_OVERLAY",
    "TC_POTHOLE_PATCHING",
    "TC_RECONSTRUCTION",
    "TC_ROUTINE_MAINTENANCE",
    "TC_SLURRY_SEAL",
    "TC_SURFACE_TREATMENT",
    "TREATMENT_CATEGORIES",
    "TreatmentRecommendation",
    "get_thresholds",
    "reset_thresholds",
    "set_thresholds",
]
