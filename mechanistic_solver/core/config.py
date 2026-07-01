"""Configuration system for the independent mechanistic solver.

Manages default numerical properties, solver thresholds, and material presets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SolverConfig:
    """Settings governing the mechanistic solver's defaults and execution properties."""
    
    # Mathematical integration defaults
    default_tolerance: float = 1e-6
    default_max_limit: int = 5000
    
    # Standard IRC evaluation settings
    standard_wheel_load_kn: float = 40.0         # 40 kN (80 kN single axle wheel load)
    standard_contact_pressure_mpa: float = 0.56   # 0.56 MPa (5.6 kg/cm2 tire pressure)
    
    # Material presets (modulus in MPa, poisson)
    material_presets: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: {
            "BC": {"modulus": 3000.0, "poisson": 0.35},
            "DBM": {"modulus": 3000.0, "poisson": 0.35},
            "WMM": {"modulus": 300.0, "poisson": 0.40},
            "GSB": {"modulus": 150.0, "poisson": 0.40},
            "Subgrade": {"modulus": 50.0, "poisson": 0.35},
        }
    )

    def get_preset(self, name: str) -> tuple[float, float] | None:
        """Helper to fetch modulus and Poisson's ratio for a known material preset.

        Args:
            name (str): Material name (e.g., 'BC', 'DBM').

        Returns:
            tuple[float, float] | None: (modulus_mpa, poisson_ratio) if found, otherwise None.
        """
        key = name.upper().strip()
        for preset_name, props in self.material_presets.items():
            if preset_name in key:
                return props["modulus"], props["poisson"]
        return None
