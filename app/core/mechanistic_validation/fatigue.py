"""Phase-14 fatigue-life model (IRC:37-2018 cl. 6.4.2 shape).

Closed-form formula:

    N_f = C * k1 * (1/eps_t)^k2 * (1/E_BC)^k3        [axle passes]
    N_f_msa = N_f / 1e6

Conventions:
    eps_t    horizontal tensile strain at bottom of the bituminous-bound
             layer, supplied here in MICRO-strain (1 µε = 1e-6); the
             absolute value is used inside the formula.
    E_BC     resilient modulus of the top bituminous course, MPa.
    C        VBE / Va adjustment factor (IRC:37-2018 cl. 6.4.2).
             Default 1.0 — engineer override on the input.

ALL CONSTANTS HERE ARE FLAGGED ``IRC37_PLACEHOLDER`` until field-
calibrated. The formula constants live on a swappable
``FatigueCalibration`` dataclass (same pattern as Phase 10
``PCICalibration`` and Phase 12 ``RehabThresholds``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.code_refs import CodeRef


PLACEHOLDER_LABEL: str = "IRC37_PLACEHOLDER_80pct"

PLACEHOLDER_NOTE: str = (
    "Fatigue calibration constants are IRC:37-2018 cl. 6.4.2 published "
    "values at 80% reliability and are tagged IRC37_PLACEHOLDER pending "
    "project-specific field calibration."
)


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:37-2018", "cl. 6.4.2", "Bituminous-layer fatigue life"),
)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FatigueCalibration:
    """Swappable container for the fatigue model constants.

    A future calibration phase replaces the active instance via
    :func:`set_fatigue_calibration` — formula, engine and reports all
    read through this single source of truth.
    """
    label: str
    k1: float
    k2: float
    k3: float
    reliability_pct: int
    is_placeholder: bool = True


# IRC:37-2018 cl. 6.4.2 — 80% reliability defaults (PLACEHOLDER).
DEFAULT_FATIGUE_CALIBRATION: FatigueCalibration = FatigueCalibration(
    label=PLACEHOLDER_LABEL,
    k1=2.21e-04,
    k2=3.89,
    k3=0.854,
    reliability_pct=80,
    is_placeholder=True,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FatigueCheck:
    """One fatigue verdict.

    ``verdict`` is ``None`` when the engine refused to emit a verdict
    (placeholder mechanistic input or missing strain). ``None`` is
    therefore meaningful — callers MUST treat it as 'no decision', not
    'pass'.
    """
    epsilon_t_microstrain: Optional[float]
    e_bc_mpa: Optional[float]
    design_msa: float
    c_factor: float
    cumulative_life_msa: Optional[float]
    verdict: Optional[str]                  # "PASS" | "FAIL" | None
    calibration: FatigueCalibration
    references: Tuple[CodeRef, ...] = REFERENCES
    is_placeholder: bool = True
    refused: bool = False
    refused_reason: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Pure formula
# ---------------------------------------------------------------------------

def compute_fatigue_life(
    epsilon_t_microstrain: float,
    e_bc_mpa: float,
    design_msa: float,
    *,
    c_factor: float = 1.0,
    calibration: FatigueCalibration = DEFAULT_FATIGUE_CALIBRATION,
    notes: str = "",
) -> FatigueCheck:
    """Apply the IRC:37-2018 fatigue formula and return a ``FatigueCheck``.

    Inputs are expected to be already-validated (positive, finite). The
    engine's refusal-gate handles invalid / placeholder upstream cases —
    this function intentionally does NOT mask zero/negative strains so
    a programming error propagates rather than silently mis-verdicts.
    """
    eps_abs = epsilon_t_microstrain * 1.0e-6
    if eps_abs <= 0 or e_bc_mpa <= 0:
        raise ValueError(
            "compute_fatigue_life requires positive strain and modulus; "
            "use the engine refusal gate for placeholder / missing inputs."
        )
    n_f = (c_factor
           * calibration.k1
           * (1.0 / eps_abs) ** calibration.k2
           * (1.0 / e_bc_mpa) ** calibration.k3)
    n_f_msa = n_f / 1.0e6
    verdict = "PASS" if n_f_msa >= design_msa else "FAIL"
    return FatigueCheck(
        epsilon_t_microstrain=float(epsilon_t_microstrain),
        e_bc_mpa=float(e_bc_mpa),
        design_msa=float(design_msa),
        c_factor=float(c_factor),
        cumulative_life_msa=float(n_f_msa),
        verdict=verdict,
        calibration=calibration,
        references=REFERENCES,
        is_placeholder=calibration.is_placeholder,
        refused=False,
        refused_reason="",
        notes=notes,
    )


def refused_fatigue_check(
    *,
    design_msa: float,
    epsilon_t_microstrain: Optional[float],
    e_bc_mpa: Optional[float],
    c_factor: float,
    calibration: FatigueCalibration,
    refused_reason: str,
    notes: str = "",
) -> FatigueCheck:
    """Build a FatigueCheck explicitly marked refused — no verdict, no life."""
    return FatigueCheck(
        epsilon_t_microstrain=epsilon_t_microstrain,
        e_bc_mpa=e_bc_mpa,
        design_msa=float(design_msa),
        c_factor=float(c_factor),
        cumulative_life_msa=None,
        verdict=None,
        calibration=calibration,
        references=REFERENCES,
        is_placeholder=True,
        refused=True,
        refused_reason=refused_reason,
        notes=notes,
    )
