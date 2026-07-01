"""Heavy industrial pavements loading templates, port reach stackers, and warehouse slab checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class IndustrialLoadTemplate:
    """Loading configurations representing heavy port or warehouse equipment."""
    equipment_name: str
    wheel_load_kn: float
    tyre_pressure_mpa: float
    contact_radius_mm: float


# Port and industrial facility loading presets
INDUSTRIAL_LOADS: Mapping[str, IndustrialLoadTemplate] = {
    "ReachStacker-Front": IndustrialLoadTemplate(
        equipment_name="Reach Stacker Front Axle Loaded",
        wheel_load_kn=250.0,
        tyre_pressure_mpa=1.0,
        contact_radius_mm=282.0
    ),
    "HeavyForklift-15T": IndustrialLoadTemplate(
        equipment_name="15-Tonne Heavy Industrial Forklift",
        wheel_load_kn=110.0,
        tyre_pressure_mpa=0.85,
        contact_radius_mm=203.0
    ),
    "StraddleCarrier": IndustrialLoadTemplate(
        equipment_name="Straddle Carrier Loaded",
        wheel_load_kn=150.0,
        tyre_pressure_mpa=0.9,
        contact_radius_mm=230.0
    )
}


class IndustrialPavementModel:
    """Calculates allowable repetition counts for heavy port/container yards and warehouse slab design checks."""

    @staticmethod
    def get_container_yard_fatigue_life(tensile_strain: float, concrete_flexural_strength_mpa: float = 4.5) -> float:
        """Estimate concrete or stabilized fatigue repetitions for container yard pavement layers.

        Formula: log10(N) = 12.0 * (1 - Stress_Ratio)
        Reference: PCA (Portland Cement Association) Design of Concrete Industrial Pavements.
        """
        stress_ratio = tensile_strain * 1e6 / 1000.0  # Simulated stress-strength ratio
        if stress_ratio >= 1.0:
            return 1.0
        if stress_ratio <= 0.45:
            return float("inf")  # Unlimited repetitions under fatigue limit
        return 10.0 ** (12.0 * (1.0 - stress_ratio))

    @staticmethod
    def get_warehouse_slab_allowable_load(
        slab_thickness_mm: float,
        flexural_strength_mpa: float = 4.0,
        modulus_of_rupture_mpa: float = 4.5
    ) -> float:
        """Estimate safe static point load limit (kN) at the center of an industrial concrete warehouse floor.

        Formula: P_allow = ( 2 * f_s * h^2 ) / ( (1 - nu) * SF )
        Reference: British Prepared Concrete Association (BPCA) Technical Report 34.
        """
        h_m = slab_thickness_mm / 1000.0
        safety_factor = 2.0
        p_allow_n = (2.0 * flexural_strength_mpa * 1e6 * h_m**2) / ((1.0 - 0.15) * safety_factor)
        return p_allow_n / 1000.0  # Convert to kN
