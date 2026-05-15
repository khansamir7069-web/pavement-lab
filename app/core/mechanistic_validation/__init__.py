"""Phase-14 mechanistic-validation package.

Consumes a Phase-13 ``MechanisticResult`` and produces a fatigue +
rutting verdict pair against IRC:37-2018 cl. 6.4 formulas, with a
hard refusal gate on placeholder mechanistic input.

Public surface is intentionally narrow — the engine is the only
recommended entry point for callers; the per-formula modules are
exposed for calibration / test code.
"""
from __future__ import annotations

from .engine import (
    MechanisticValidationInput,
    MechanisticValidationSummary,
    PLACEHOLDER_NOTE,
    REFERENCES,
    REFUSED_MISSING_E_BC,
    REFUSED_MISSING_STRAIN,
    REFUSED_PLACEHOLDER_MECH,
    compute_mechanistic_validation,
    get_fatigue_calibration,
    get_rutting_calibration,
    reset_fatigue_calibration,
    reset_rutting_calibration,
    set_fatigue_calibration,
    set_rutting_calibration,
)
from .fatigue import (
    DEFAULT_FATIGUE_CALIBRATION,
    FatigueCalibration,
    FatigueCheck,
    compute_fatigue_life,
    refused_fatigue_check,
)
from .rutting import (
    DEFAULT_RUTTING_CALIBRATION,
    RuttingCalibration,
    RuttingCheck,
    compute_rutting_life,
    refused_rutting_check,
)
from .strains import (
    LABEL_FATIGUE,
    LABEL_RUTTING,
    StrainExtraction,
    extract_fatigue_strain,
    extract_rutting_strain,
)

__all__ = [
    # engine
    "MechanisticValidationInput",
    "MechanisticValidationSummary",
    "compute_mechanistic_validation",
    "PLACEHOLDER_NOTE",
    "REFERENCES",
    "REFUSED_PLACEHOLDER_MECH",
    "REFUSED_MISSING_STRAIN",
    "REFUSED_MISSING_E_BC",
    "get_fatigue_calibration",
    "set_fatigue_calibration",
    "reset_fatigue_calibration",
    "get_rutting_calibration",
    "set_rutting_calibration",
    "reset_rutting_calibration",
    # fatigue
    "FatigueCalibration",
    "FatigueCheck",
    "DEFAULT_FATIGUE_CALIBRATION",
    "compute_fatigue_life",
    "refused_fatigue_check",
    # rutting
    "RuttingCalibration",
    "RuttingCheck",
    "DEFAULT_RUTTING_CALIBRATION",
    "compute_rutting_life",
    "refused_rutting_check",
    # strains
    "StrainExtraction",
    "extract_fatigue_strain",
    "extract_rutting_strain",
    "LABEL_FATIGUE",
    "LABEL_RUTTING",
]
