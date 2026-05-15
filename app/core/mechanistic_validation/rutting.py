"""Phase-14 rutting-life model (IRC:37-2018 cl. 6.4.3 shape).

Closed-form formula:

    N_r = k_r * (1 / eps_v)^k_v                  [axle passes]
    N_r_msa = N_r / 1e6

eps_v is the vertical compressive strain at top of the subgrade,
supplied here in MICRO-strain; the formula uses the absolute value.

ALL CONSTANTS HERE ARE FLAGGED ``IRC37_PLACEHOLDER`` until field-
calibrated. The constants live on a swappable ``RuttingCalibration``
dataclass (same pattern as Phase 10 ``PCICalibration`` and Phase 12
``RehabThresholds``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.code_refs import CodeRef


PLACEHOLDER_LABEL: str = "IRC37_PLACEHOLDER_80pct"

PLACEHOLDER_NOTE: str = (
    "Rutting calibration constants are IRC:37-2018 cl. 6.4.3 published "
    "values at 80% reliability and are tagged IRC37_PLACEHOLDER pending "
    "project-specific field calibration."
)


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:37-2018", "cl. 6.4.3", "Subgrade rutting life"),
)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RuttingCalibration:
    """Swappable container for the rutting model constants."""
    label: str
    k_r: float
    k_v: float
    reliability_pct: int
    is_placeholder: bool = True


# IRC:37-2018 cl. 6.4.3 — 80% reliability defaults (PLACEHOLDER).
DEFAULT_RUTTING_CALIBRATION: RuttingCalibration = RuttingCalibration(
    label=PLACEHOLDER_LABEL,
    k_r=4.1656e-08,
    k_v=4.5337,
    reliability_pct=80,
    is_placeholder=True,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RuttingCheck:
    """One rutting verdict.

    ``verdict`` is ``None`` when the engine refused to emit a verdict
    (placeholder mechanistic input or missing strain). Callers MUST
    treat ``None`` as 'no decision', not 'pass'.
    """
    epsilon_v_microstrain: Optional[float]
    design_msa: float
    cumulative_life_msa: Optional[float]
    verdict: Optional[str]                  # "PASS" | "FAIL" | None
    calibration: RuttingCalibration
    references: Tuple[CodeRef, ...] = REFERENCES
    is_placeholder: bool = True
    refused: bool = False
    refused_reason: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Pure formula
# ---------------------------------------------------------------------------

def compute_rutting_life(
    epsilon_v_microstrain: float,
    design_msa: float,
    *,
    calibration: RuttingCalibration = DEFAULT_RUTTING_CALIBRATION,
    notes: str = "",
) -> RuttingCheck:
    """Apply the IRC:37-2018 rutting formula and return a ``RuttingCheck``."""
    eps_abs = epsilon_v_microstrain * 1.0e-6
    if eps_abs <= 0:
        raise ValueError(
            "compute_rutting_life requires positive strain; "
            "use the engine refusal gate for placeholder / missing inputs."
        )
    n_r = calibration.k_r * (1.0 / eps_abs) ** calibration.k_v
    n_r_msa = n_r / 1.0e6
    verdict = "PASS" if n_r_msa >= design_msa else "FAIL"
    return RuttingCheck(
        epsilon_v_microstrain=float(epsilon_v_microstrain),
        design_msa=float(design_msa),
        cumulative_life_msa=float(n_r_msa),
        verdict=verdict,
        calibration=calibration,
        references=REFERENCES,
        is_placeholder=calibration.is_placeholder,
        refused=False,
        refused_reason="",
        notes=notes,
    )


def refused_rutting_check(
    *,
    design_msa: float,
    epsilon_v_microstrain: Optional[float],
    calibration: RuttingCalibration,
    refused_reason: str,
    notes: str = "",
) -> RuttingCheck:
    """Build a RuttingCheck explicitly marked refused — no verdict, no life."""
    return RuttingCheck(
        epsilon_v_microstrain=epsilon_v_microstrain,
        design_msa=float(design_msa),
        cumulative_life_msa=None,
        verdict=None,
        calibration=calibration,
        references=REFERENCES,
        is_placeholder=True,
        refused=True,
        refused_reason=refused_reason,
        notes=notes,
    )
