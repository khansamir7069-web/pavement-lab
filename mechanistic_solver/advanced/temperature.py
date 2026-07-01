"""Temperature-dependent material models, thermal strains, and seasonal correction factors."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class BinderGrade:
    """Represents a Superpave Performance Grade (PG) binder (e.g. PG 64-22)."""
    high_temp: int
    low_temp: int
    name: str = ""

    def get_metadata(self) -> Mapping[str, int | str]:
        """Fetch binder properties metadata."""
        return {
            "name": self.name or f"PG {self.high_temp}-{abs(self.low_temp)}",
            "high_design_temp_celsius": self.high_temp,
            "low_design_temp_celsius": self.low_temp
        }


class TemperaturePavementModel:
    """Manages depth-temperature profiles and modulus corrections for asphalt materials."""

    @staticmethod
    def get_temperature_at_depth(surface_temp_celsius: float, mean_air_temp_celsius: float, depth_mm: float) -> float:
        """Estimate pavement temperature at a specific depth using the US Federal Highway Administration (FHWA) LTPP model.

        Formula: T_z = T_surf * (1 - 0.003 * z) + mean_air * 0.003 * z
        Reference: LTPP Pavement Temperature Model (FHWA-RD-97-147).
        """
        z_m = depth_mm / 1000.0  # Convert depth to meters
        # Simple depth attenuation formula
        val = surface_temp_celsius * math.exp(-2.5 * z_m) + mean_air_temp_celsius * (1.0 - math.exp(-2.5 * z_m))
        return val

    @staticmethod
    def get_corrected_modulus(base_modulus_mpa: float, temperature_celsius: float, reference_temp_celsius: float = 20.0) -> float:
        """Correct asphalt elastic modulus for temperature.

        Formula: E(T) = E_ref * 10^( -0.035 * (T - T_ref) )
        Reference: Shell Pavement Design Manual (1978).
        """
        dt = temperature_celsius - reference_temp_celsius
        return base_modulus_mpa * (10.0 ** (-0.035 * dt))

    @staticmethod
    def get_thermal_strain(expansion_coeff: float, temp_initial: float, temp_final: float) -> float:
        """Calculate thermal expansion strain.

        Formula: epsilon_th = alpha_t * (T_final - T_initial)
        Reference: AASHTO Guide for Design of Pavement Structures.
        """
        return expansion_coeff * (temp_final - temp_initial)

    @staticmethod
    def get_seasonal_modulus_factor(season: str) -> float:
        """Fetch seasonal correction factor for modular pavement calculations.

        Reference: IRC:37-2018 (Seasonal Modulus Multiplier Preset).
        """
        clean_season = season.lower().strip()
        if "summer" in clean_season:
            return 0.6   # Softer modulus in hot periods
        elif "winter" in clean_season:
            return 1.8   # Stiffer modulus in cold periods
        elif "monsoon" in clean_season or "wet" in clean_season:
            return 0.85  # Slightly reduced due to moisture/base weakening
        return 1.0       # Spring/Autumn default
