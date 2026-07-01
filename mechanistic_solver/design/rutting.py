"""IRC:37 subgrade rutting failure model implementation."""
from __future__ import annotations

import math
from typing import Any, Mapping


def compute_rutting_life(
    epsilon_v: float,       # unitless vertical strain
    k_r: float = 4.1656e-8,  # default IRC:37 default (80% reliability)
    k_v: float = 4.5337
) -> float:
    """Calculate allowable rutting repetitions N_r according to IRC:37-2018.

    N_r = k_r * (1 / eps_v)^k_v
    """
    if epsilon_v <= 0.0:
        # If strain is zero or negative (tension), subgrade rutting damage is zero/infinite life
        return float("inf")
        
    n_r = k_r * (1.0 / epsilon_v) ** k_v
    return n_r


def check_rutting_adequacy(
    epsilon_v: float,
    design_traffic_msa: float,
    k_r: float = 4.1656e-8,
    k_v: float = 4.5337
) -> Mapping[str, Any]:
    """Perform rutting adequacy check against design traffic in MSA."""
    if design_traffic_msa < 0.0:
        raise ValueError("Design traffic in MSA must be non-negative.")
        
    n_r = compute_rutting_life(epsilon_v, k_r, k_v)
    n_r_msa = n_r / 1.0e6 if math.isfinite(n_r) else float("inf")
    
    utilization = 0.0
    if n_r_msa > 0.0:
        utilization = design_traffic_msa / n_r_msa if math.isfinite(n_r_msa) else 0.0
        
    passed = n_r_msa >= design_traffic_msa
    
    notes = (
        f"Rutting check: Allowable={n_r_msa:.2f} MSA, Design={design_traffic_msa:.2f} MSA. "
        f"Utilization={utilization*100.1:.1f}%."
    )
    
    return {
        "allowable_repetitions": n_r,
        "allowable_repetitions_msa": n_r_msa,
        "design_traffic_msa": design_traffic_msa,
        "utilization_ratio": utilization,
        "passed": passed,
        "notes": notes
    }
