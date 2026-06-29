"""Cement-Treated Base (CTB) and Cement-Treated Sub-base (CTS) design calculations.

This module implements the calculation core, validation rules, and flexible comparison
routines for the stabilized pavement design module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional, TYPE_CHECKING

from .structural_design import PavementLayer
from .intelligence_checker import IntelligenceResult

if TYPE_CHECKING:
    from .mechanistic_validation import MechanisticValidationSummary


@dataclass(frozen=True, slots=True)
class StabilizedInput:
    ctb_thickness_mm: float
    ctb_modulus_mpa: float
    ctb_ucs_mpa: float                  # Unconfined Compressive Strength (strength in MPa)
    ctb_poisson: float = 0.25
    cts_class: str = "C1.5/2.0"         # strength class / grade
    cts_thickness_mm: float = 100.0
    cts_modulus_mpa: float = 3000.0
    cts_poisson: float = 0.25
    gsb_thickness_mm: float = 150.0
    bituminous_thickness_mm: float = 100.0
    flexible_design_msa: float = 10.0
    flexible_subgrade_cbr: float = 5.0
    notes: str = ""

    def __post_init__(self) -> None:
        # Physical invalidity checks only (raise ValueError)
        if self.ctb_thickness_mm <= 0:
            raise ValueError("CTB thickness must be > 0 mm.")
        if self.ctb_modulus_mpa <= 0:
            raise ValueError("CTB modulus must be > 0 MPa.")
        if self.ctb_ucs_mpa < 0:
            raise ValueError("CTB UCS cannot be negative.")
        if self.ctb_poisson <= 0 or self.ctb_poisson >= 0.5:
            raise ValueError("CTB Poisson's ratio must be between 0 and 0.5.")
        if self.cts_thickness_mm <= 0:
            raise ValueError("CTS thickness must be > 0 mm.")
        if self.cts_modulus_mpa <= 0:
            raise ValueError("CTS modulus must be > 0 MPa.")
        if self.cts_poisson <= 0 or self.cts_poisson >= 0.5:
            raise ValueError("CTS Poisson's ratio must be between 0 and 0.5.")
        if self.gsb_thickness_mm <= 0:
            raise ValueError("GSB thickness must be > 0 mm.")
        if self.bituminous_thickness_mm <= 0:
            raise ValueError("Bituminous cover thickness must be > 0 mm.")
        if self.flexible_design_msa <= 0:
            raise ValueError("Flexible design traffic (MSA) must be > 0.")
        if self.flexible_subgrade_cbr <= 0:
            raise ValueError("Flexible subgrade CBR (%) must be > 0.")


@dataclass(frozen=True, slots=True)
class StabilizedResult:
    inputs: StabilizedInput
    warnings: Tuple[str, ...]
    thickness_savings_mm: float
    thickness_savings_pct: float
    conventional_composition: Tuple[PavementLayer, ...]
    stabilized_composition: Tuple[PavementLayer, ...]
    validation_mode: str = "Decision Support Mode"
    comparison_label: str = "Indicative comparison against conventional flexible pavement"
    safety_disclaimer: str = (
        "This design is for decision support only. Independent engineering verification "
        "is required before field execution."
    )
    intelligence: Optional[IntelligenceResult] = None
    mechanistic_validation: "Optional[MechanisticValidationSummary]" = None


def compute_stabilized_design(
    inp: StabilizedInput,
    has_mechanistic_validation: bool = False,
    mechanistic_validation: "Optional[MechanisticValidationSummary]" = None,
) -> StabilizedResult:
    """Compute stabilized pavement design values, safety warnings, and side-by-side comparison."""
    from app.core.catalogue.engine import lookup_catalogue_design
    # 1. Engineering warnings (screening only, not raising ValueError)
    warnings_list = []

    # Missing UCS
    if inp.ctb_ucs_mpa == 0:
        warnings_list.append(
            "Missing UCS: Unconfined Compressive Strength (UCS) must be specified for "
            "Cement Treated Base (CTB) design. Typical values range from 3.0 to 7.0 MPa."
        )

    # Unrealistic Modulus
    if inp.ctb_modulus_mpa < 3000 or inp.ctb_modulus_mpa > 15000:
        warnings_list.append(
            f"Unrealistic CTB modulus: elastic modulus ({inp.ctb_modulus_mpa:.0f} MPa) is outside "
            f"the typical engineering range of 3000 to 15000 MPa."
        )
    if inp.cts_modulus_mpa < 1000 or inp.cts_modulus_mpa > 6000:
        warnings_list.append(
            f"Unrealistic CTS modulus: elastic modulus ({inp.cts_modulus_mpa:.0f} MPa) is outside "
            f"the typical engineering range of 1000 to 6000 MPa."
        )

    # Invalid Poisson's ratio warning (typical values: 0.25)
    if inp.ctb_poisson < 0.15 or inp.ctb_poisson > 0.35:
        warnings_list.append(
            f"Non-standard CTB Poisson's ratio: value ({inp.ctb_poisson:.2f}) is outside the typical "
            f"stabilized pavement range of 0.15 to 0.35."
        )
    if inp.cts_poisson < 0.15 or inp.cts_poisson > 0.35:
        warnings_list.append(
            f"Non-standard CTS Poisson's ratio: value ({inp.cts_poisson:.2f}) is outside the typical "
            f"stabilized pavement range of 0.15 to 0.35."
        )

    # Very low thickness warnings
    if inp.ctb_thickness_mm < 100:
        warnings_list.append(
            f"Very low CTB thickness: Cement-Treated Base thickness ({inp.ctb_thickness_mm:.0f} mm) "
            f"is below the recommended structural minimum of 100 mm."
        )
    if inp.cts_thickness_mm < 100:
        warnings_list.append(
            f"Very low CTS thickness: Cement-Treated Sub-base thickness ({inp.cts_thickness_mm:.0f} mm) "
            f"is below the recommended structural minimum of 100 mm."
        )

    # Fatigue check preliminary notice
    warnings_list.append(
        "CTB Fatigue Check (Preliminary): Fatigue cracking validation is not fully verified from empirical "
        "inputs. Complete fatigue checks require mechanistic IITPAVE strain analysis."
    )

    # General review warning
    warnings_list.append(
        "Engineer review required: Cement-stabilized base/sub-base designs must be verified "
        "through local material trials and mechanistic analysis."
    )

    # 2. Get baseline flexible design from catalogue lookup engine
    try:
        baseline = lookup_catalogue_design(inp.flexible_design_msa, inp.flexible_subgrade_cbr)
        flexible_comp = baseline.composition
    except Exception:
        # Fallback if lookup fails (e.g. empty catalogue)
        flexible_comp = (
            PavementLayer(name="Bituminous Cover", thickness_mm=100.0, material="BC/DBM", modulus_mpa=3000.0),
            PavementLayer(name="Granular Base", thickness_mm=250.0, material="WMM", modulus_mpa=350.0),
            PavementLayer(name="Granular Sub-base", thickness_mm=200.0, material="GSB", modulus_mpa=150.0),
        )

    # 3. Create stabilized design layer stack
    stabilized_comp = (
        PavementLayer(
            name="Bituminous Cover",
            thickness_mm=inp.bituminous_thickness_mm,
            material="BC/DBM",
            modulus_mpa=3000.0,
            poisson=0.35,
        ),
        PavementLayer(
            name="Cement Treated Base (CTB)",
            thickness_mm=inp.ctb_thickness_mm,
            material="CTB",
            modulus_mpa=inp.ctb_modulus_mpa,
            poisson=inp.ctb_poisson,
        ),
        PavementLayer(
            name="Cement Treated Sub-base (CTS)",
            thickness_mm=inp.cts_thickness_mm,
            material="CTS",
            modulus_mpa=inp.cts_modulus_mpa,
            poisson=inp.cts_poisson,
        ),
        PavementLayer(
            name="Granular Sub-base",
            thickness_mm=inp.gsb_thickness_mm,
            material="GSB",
            modulus_mpa=150.0,
            poisson=0.35,
        ),
    )

    # 4. Calculate savings
    total_flexible = sum(l.thickness_mm for l in flexible_comp)
    total_stabilized = sum(l.thickness_mm for l in stabilized_comp)

    savings_mm = total_flexible - total_stabilized
    savings_pct = (savings_mm / total_flexible * 100.0) if total_flexible > 0 else 0.0

    # 5. Validation mode
    has_mech = has_mechanistic_validation or (
        mechanistic_validation is not None
        and not mechanistic_validation.is_placeholder
        and not mechanistic_validation.refused
    )
    mode = "Mechanistic Verified Mode" if has_mech else "Decision Support Mode"

    from app.core.intelligence_checker import check_pavement_intelligence
    from app.core.structural_design import compute_subgrade_mr
    mr = compute_subgrade_mr(inp.flexible_subgrade_cbr)
    intel = check_pavement_intelligence(stabilized_comp, mr)

    return StabilizedResult(
        inputs=inp,
        warnings=tuple(warnings_list),
        thickness_savings_mm=savings_mm,
        thickness_savings_pct=savings_pct,
        conventional_composition=flexible_comp,
        stabilized_composition=stabilized_comp,
        validation_mode=mode,
        intelligence=intel,
        mechanistic_validation=mechanistic_validation,
    )
