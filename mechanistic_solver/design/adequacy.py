"""Structural adequacy engine combining fatigue and rutting verification models."""
from __future__ import annotations

from typing import Any, Mapping

from mechanistic_solver.design.fatigue import check_fatigue_adequacy
from mechanistic_solver.design.rutting import check_rutting_adequacy


def check_structural_adequacy(
    epsilon_t: float,           # unitless tensile strain at bottom of bituminous
    e_bc_mpa: float,            # bituminous layer modulus, MPa
    epsilon_v: float,           # unitless vertical strain at top of subgrade
    design_traffic_msa: float,  # design traffic, MSA
    c_factor: float = 1.0,
    warnings: list[str] | None = None
) -> Mapping[str, Any]:
    """Evaluate structural adequacy of pavement against fatigue and rutting criteria."""
    if warnings is None:
        warnings = []
        
    # 1. Traffic validation
    if design_traffic_msa <= 0.0:
        warnings.append("Design traffic is zero or negative. Evaluation might be trivial.")
        design_traffic_msa = max(0.001, design_traffic_msa)  # clamp to a small positive value if needed or keep 0.0

    # 2. Strain validations
    if epsilon_t <= 0.0:
        warnings.append("Tensile strain is zero or negative. Fatigue damage is negligible.")
    if epsilon_v <= 0.0:
        warnings.append("Vertical compressive strain is zero or negative. Rutting damage is negligible.")

    # 3. Compute fatigue and rutting responses
    fatigue_chk = check_fatigue_adequacy(epsilon_t, e_bc_mpa, design_traffic_msa, c_factor=c_factor)
    rutting_chk = check_rutting_adequacy(epsilon_v, design_traffic_msa)

    # 4. Determine governing failure mode
    fatigue_util = fatigue_chk["utilization_ratio"]
    rutting_util = rutting_chk["utilization_ratio"]
    
    if fatigue_util > rutting_util:
        governing_mode = "fatigue"
    elif rutting_util > fatigue_util:
        governing_mode = "rutting"
    else:
        governing_mode = "none"

    overall_passed = fatigue_chk["passed"] and rutting_chk["passed"]

    # 5. Build traceability notes
    trace_notes = (
        f"Structural verification: Overall verdict={'PASS' if overall_passed else 'FAIL'}. "
        f"Governing mode is {governing_mode.upper()} "
        f"(Fatigue Util={fatigue_util*100.1:.1f}%, Rutting Util={rutting_util*100.1:.1f}%)."
    )

    return {
        "fatigue_status": fatigue_chk,
        "rutting_status": rutting_chk,
        "governing_failure_mode": governing_mode,
        "overall_passed": overall_passed,
        "utilization_ratios": {
            "fatigue": fatigue_util,
            "rutting": rutting_util
        },
        "warnings": warnings,
        "traceability_notes": trace_notes
    }
