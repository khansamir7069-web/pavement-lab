"""Phase-14 mechanistic-validation engine.

Composes the four building blocks (strain extractor, fatigue formula,
rutting formula, refusal gate) into ``compute_mechanistic_validation``.

Critical safety contract (Phase 14 spec point 3):
    if mech_result.is_placeholder is True
        -> return a MechanisticValidationSummary whose
           both checks have verdict=None, life=None, refused=True
        -> NEVER raise (per approved decision 5)
        -> NEVER substitute numbers silently
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.code_refs import CodeRef
from app.core.iitpave import (
    MechanisticResult,
    PavementStructure,
)

from .fatigue import (
    DEFAULT_FATIGUE_CALIBRATION,
    FatigueCalibration,
    FatigueCheck,
    REFERENCES as FATIGUE_REFERENCES,
    compute_fatigue_life,
    refused_fatigue_check,
)
from .rutting import (
    DEFAULT_RUTTING_CALIBRATION,
    REFERENCES as RUTTING_REFERENCES,
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


REFERENCES: Tuple[CodeRef, ...] = (
    *FATIGUE_REFERENCES,
    *RUTTING_REFERENCES,
    CodeRef("IRC:37-2018", "cl. 6.4", "Mechanistic-empirical validation framework"),
)


PLACEHOLDER_NOTE: str = (
    "Mechanistic-validation verdicts are emitted with IRC37_PLACEHOLDER "
    "calibration constants. Field-calibrated constants must be supplied "
    "via set_fatigue_calibration / set_rutting_calibration before "
    "adopting any PASS verdict for design certification."
)


# Public reason strings (matched against in smoke + future report layer)
REFUSED_PLACEHOLDER_MECH: str = (
    "Mechanistic result flagged placeholder mechanistic input "
    "(MechanisticResult.is_placeholder=True). Final verdict refused."
)
REFUSED_MISSING_STRAIN: str = (
    "Required strain could not be extracted from the mechanistic result; "
    "verdict refused."
)
REFUSED_MISSING_E_BC: str = (
    "No bituminous-bound modulus available in the PavementStructure; "
    "fatigue verdict refused."
)


# ---------------------------------------------------------------------------
# Active calibrations — mirror Phase 10 / Phase 12 calibration pattern
# ---------------------------------------------------------------------------

_ACTIVE_FATIGUE_CALIBRATION: FatigueCalibration = DEFAULT_FATIGUE_CALIBRATION
_ACTIVE_RUTTING_CALIBRATION: RuttingCalibration = DEFAULT_RUTTING_CALIBRATION


def get_fatigue_calibration() -> FatigueCalibration:
    return _ACTIVE_FATIGUE_CALIBRATION


def set_fatigue_calibration(c: FatigueCalibration) -> FatigueCalibration:
    global _ACTIVE_FATIGUE_CALIBRATION
    prev = _ACTIVE_FATIGUE_CALIBRATION
    _ACTIVE_FATIGUE_CALIBRATION = c
    return prev


def reset_fatigue_calibration() -> None:
    set_fatigue_calibration(DEFAULT_FATIGUE_CALIBRATION)


def get_rutting_calibration() -> RuttingCalibration:
    return _ACTIVE_RUTTING_CALIBRATION


def set_rutting_calibration(c: RuttingCalibration) -> RuttingCalibration:
    global _ACTIVE_RUTTING_CALIBRATION
    prev = _ACTIVE_RUTTING_CALIBRATION
    _ACTIVE_RUTTING_CALIBRATION = c
    return prev


def reset_rutting_calibration() -> None:
    set_rutting_calibration(DEFAULT_RUTTING_CALIBRATION)


# ---------------------------------------------------------------------------
# Input / Output dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MechanisticValidationInput:
    """Inputs to :func:`compute_mechanistic_validation`.

    ``point_labels`` (optional) parallels ``mech_result.point_results`` and
    lets the strain extractor resolve evaluation points by label
    (typically ``("bottom_of_BT", "top_of_subgrade")``). If omitted the
    strain extractor falls back to first/last-point heuristic and emits
    a traceability warning into the result notes.
    """
    mech_result: MechanisticResult
    structure: PavementStructure
    design_msa: float
    c_factor: float = 1.0
    point_labels: Optional[Tuple[str, ...]] = None
    fatigue_calibration: Optional[FatigueCalibration] = None
    rutting_calibration: Optional[RuttingCalibration] = None


@dataclass(frozen=True, slots=True)
class MechanisticValidationSummary:
    fatigue: FatigueCheck
    rutting: RuttingCheck
    is_placeholder: bool
    refused: bool
    refused_reason: str
    references: Tuple[CodeRef, ...] = REFERENCES
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_bituminous_modulus_mpa(structure: PavementStructure) -> Optional[float]:
    """Return the modulus of the topmost bituminous-bound layer.

    Heuristic: first finite-thickness layer whose ``material`` starts
    with BC / DBM / SMA (case-insensitive). Returns None when none
    matches — callers MUST refuse the fatigue verdict.
    """
    for layer in structure.layers[:-1]:
        mat = (layer.material or "").upper()
        if any(mat.startswith(tag) for tag in ("BC", "DBM", "SMA")):
            return float(layer.modulus_mpa)
    return None


def _combine_notes(*chunks: str) -> str:
    return " | ".join(c for c in chunks if c)


# ---------------------------------------------------------------------------
# The composer + safety gate
# ---------------------------------------------------------------------------

def compute_mechanistic_validation(
    inp: MechanisticValidationInput,
) -> MechanisticValidationSummary:
    """Apply the refusal gate, extract strains, run fatigue + rutting.

    Returns the summary directly — never raises on placeholder /
    missing-input flows (per approved decision 5). Callers inspect
    ``summary.refused`` / ``summary.fatigue.refused`` /
    ``summary.rutting.refused`` to detect non-verdicts.
    """
    fcal = inp.fatigue_calibration or get_fatigue_calibration()
    rcal = inp.rutting_calibration or get_rutting_calibration()

    # --- Refusal gate 1: placeholder mechanistic input -----------------
    if inp.mech_result.is_placeholder:
        fatigue = refused_fatigue_check(
            design_msa=inp.design_msa,
            epsilon_t_microstrain=None,
            e_bc_mpa=None,
            c_factor=inp.c_factor,
            calibration=fcal,
            refused_reason=REFUSED_PLACEHOLDER_MECH,
        )
        rutting = refused_rutting_check(
            design_msa=inp.design_msa,
            epsilon_v_microstrain=None,
            calibration=rcal,
            refused_reason=REFUSED_PLACEHOLDER_MECH,
        )
        return MechanisticValidationSummary(
            fatigue=fatigue,
            rutting=rutting,
            is_placeholder=True,
            refused=True,
            refused_reason=REFUSED_PLACEHOLDER_MECH,
            notes=PLACEHOLDER_NOTE,
        )

    # --- Strain extraction (may emit fallback warnings) ----------------
    ex_t: StrainExtraction = extract_fatigue_strain(
        inp.mech_result, point_labels=inp.point_labels,
    )
    ex_v: StrainExtraction = extract_rutting_strain(
        inp.mech_result, point_labels=inp.point_labels,
    )

    e_bc = _top_bituminous_modulus_mpa(inp.structure)

    # --- Fatigue branch -------------------------------------------------
    fatigue: FatigueCheck
    if ex_t.value_microstrain is None or ex_t.value_microstrain <= 0:
        fatigue = refused_fatigue_check(
            design_msa=inp.design_msa,
            epsilon_t_microstrain=ex_t.value_microstrain,
            e_bc_mpa=e_bc,
            c_factor=inp.c_factor,
            calibration=fcal,
            refused_reason=REFUSED_MISSING_STRAIN,
            notes=_combine_notes(ex_t.warning),
        )
    elif e_bc is None:
        fatigue = refused_fatigue_check(
            design_msa=inp.design_msa,
            epsilon_t_microstrain=ex_t.value_microstrain,
            e_bc_mpa=None,
            c_factor=inp.c_factor,
            calibration=fcal,
            refused_reason=REFUSED_MISSING_E_BC,
            notes=_combine_notes(ex_t.warning),
        )
    else:
        fatigue = compute_fatigue_life(
            epsilon_t_microstrain=ex_t.value_microstrain,
            e_bc_mpa=e_bc,
            design_msa=inp.design_msa,
            c_factor=inp.c_factor,
            calibration=fcal,
            notes=_combine_notes(ex_t.warning),
        )

    # --- Rutting branch -------------------------------------------------
    rutting: RuttingCheck
    if ex_v.value_microstrain is None or ex_v.value_microstrain <= 0:
        rutting = refused_rutting_check(
            design_msa=inp.design_msa,
            epsilon_v_microstrain=ex_v.value_microstrain,
            calibration=rcal,
            refused_reason=REFUSED_MISSING_STRAIN,
            notes=_combine_notes(ex_v.warning),
        )
    else:
        rutting = compute_rutting_life(
            epsilon_v_microstrain=ex_v.value_microstrain,
            design_msa=inp.design_msa,
            calibration=rcal,
            notes=_combine_notes(ex_v.warning),
        )

    # --- Summary --------------------------------------------------------
    refused = fatigue.refused or rutting.refused
    placeholder = (
        fatigue.is_placeholder or rutting.is_placeholder or refused
    )
    if refused:
        reason_chunks: list[str] = []
        if fatigue.refused:
            reason_chunks.append(f"fatigue: {fatigue.refused_reason}")
        if rutting.refused:
            reason_chunks.append(f"rutting: {rutting.refused_reason}")
        refused_reason = " | ".join(reason_chunks)
    else:
        refused_reason = ""
    notes_chunks: list[str] = []
    if placeholder:
        notes_chunks.append(PLACEHOLDER_NOTE)
    if ex_t.fallback_used or ex_v.fallback_used:
        notes_chunks.append(
            "Strain extractor used fallback resolution — see fatigue/"
            "rutting check notes for traceability."
        )
    return MechanisticValidationSummary(
        fatigue=fatigue,
        rutting=rutting,
        is_placeholder=placeholder,
        refused=refused,
        refused_reason=refused_reason,
        notes=_combine_notes(*notes_chunks),
    )
