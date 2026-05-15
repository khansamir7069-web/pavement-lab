"""Pavement Condition Survey + Distress Assessment — Phase 10 foundation.

Independent module. Reuses Phase-6 ``CodeRef`` source-tagging. Adds a
PCI-style 0-100 scoring foundation with PLACEHOLDER deduct-value
weights (ASTM D6433 shape, weights to be calibrated against an
empirical distress dataset in a future phase).
"""
from .distress_types import (
    DISTRESS_TYPES,
    SEVERITY_LEVELS,
    DistressType,
    PCICalibration,
    DEFAULT_CALIBRATION,
    get_calibration,
    set_calibration,
    reset_calibration,
    RECALIBRATE_ME,
    PLACEHOLDER_NOTE,
)
from .engine import (
    DistressRecord,
    ConditionSurveyInput,
    ConditionSurveyResult,
    PerDistressBreakdown,
    compute_condition_survey,
    condition_category,
    REFERENCES,
)
from .rehab_recommendations import RehabRecommendation, recommend_rehab

__all__ = [
    "DISTRESS_TYPES",
    "SEVERITY_LEVELS",
    "DistressType",
    "PCICalibration",
    "DEFAULT_CALIBRATION",
    "get_calibration",
    "set_calibration",
    "reset_calibration",
    "RECALIBRATE_ME",
    "PLACEHOLDER_NOTE",
    "DistressRecord",
    "ConditionSurveyInput",
    "ConditionSurveyResult",
    "PerDistressBreakdown",
    "compute_condition_survey",
    "condition_category",
    "REFERENCES",
    "RehabRecommendation",
    "recommend_rehab",
]
