"""IRC:37 fatigue cracking failure model implementation."""
from __future__ import annotations

import math
from typing import Any, Mapping


def compute_fatigue_life(
    epsilon_t: float,       # unitless tensile strain
    e_bc_mpa: float,        # bituminous layer modulus, MPa
    c_factor: float = 1.0,
    k1: float = 2.21e-4,    # default IRC:37 default (80% reliability)
    k2: float = 3.89,
    k3: float = 0.854
) -> float:
    """Calculate allowable fatigue repetitions N_f according to IRC:37-2018.

    N_f = C * k1 * (1 / eps_t)^k2 * (1 / E_BC)^k3
    """
    if epsilon_t <= 0.0:
        # If strain is zero or negative (compressive), fatigue damage is zero/infinite life
        return float("inf")
    if e_bc_mpa <= 0.0:
        raise ValueError("Bituminous layer elastic modulus must be positive.")
        
    n_f = c_factor * k1 * (1.0 / epsilon_t) ** k2 * (1.0 / e_bc_mpa) ** k3
    return n_f


def check_fatigue_adequacy(
    epsilon_t: float,
    e_bc_mpa: float,
    design_traffic_msa: float,
    c_factor: float = 1.0,
    k1: float = 2.21e-4,
    k2: float = 3.89,
    k3: float = 0.854
) -> Mapping[str, Any]:
    """Perform fatigue adequacy check against design traffic in MSA."""
    if design_traffic_msa < 0.0:
        raise ValueError("Design traffic in MSA must be non-negative.")
        
    n_f = compute_fatigue_life(epsilon_t, e_bc_mpa, c_factor, k1, k2, k3)
    n_f_msa = n_f / 1.0e6 if math.isfinite(n_f) else float("inf")
    
    utilization = 0.0
    if n_f_msa > 0.0:
        utilization = design_traffic_msa / n_f_msa if math.isfinite(n_f_msa) else 0.0
        
    passed = n_f_msa >= design_traffic_msa
    
    notes = (
        f"Fatigue check: Allowable={n_f_msa:.2f} MSA, Design={design_traffic_msa:.2f} MSA. "
        f"Utilization={utilization*100.1:.1f}%."
    )
    
    return {
        "allowable_repetitions": n_f,
        "allowable_repetitions_msa": n_f_msa,
        "design_traffic_msa": design_traffic_msa,
        "utilization_ratio": utilization,
        "passed": passed,
        "notes": notes
    }
