"""Dynamic loading models, harmonic/impulse wheel loads, and speed-frequency conversions."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DynamicWheelLoad:
    """Represents a wheel load with dynamic time-varying components."""
    base_load_kn: float
    tyre_pressure_mpa: float
    contact_radius_mm: float
    frequency_hz: float = 10.0  # Default frequency of harmonic loading (Hz)
    speed_kmh: float = 60.0      # Vehicle speed for frequency calculation (km/h)

    def get_angular_frequency(self) -> float:
        """Get angular frequency omega (rad/s)."""
        return 2.0 * math.pi * self.frequency_hz

    def get_loading_time_duration(self) -> float:
        """Estimate the duration of loading pulse at a point based on vehicle speed.

        Formula: t = 2 * a / v
        where:
          a = tyre contact radius
          v = speed in m/s
        Reference: Barksdale, R.D. (1971). Compressive Stress Pulses in Flexible Pavement.
        """
        speed_ms = self.speed_kmh / 3.6
        if speed_ms <= 0.0:
            return float("inf")
        radius_m = self.contact_radius_mm / 1000.0
        return (2.0 * radius_m) / speed_ms

    def get_equivalent_frequency(self) -> float:
        """Convert vehicle speed to equivalent load frequency.

        Formula: f = 1 / (2 * pi * t)
        Reference: Brown, S.F. (1973). Determination of Young's Modulus for Asphalt.
        """
        duration = self.get_loading_time_duration()
        if math.isinf(duration) or duration <= 0.0:
            return 1e-5
        return 1.0 / (2.0 * math.pi * duration)

    def get_harmonic_load_at_time(self, t: float) -> float:
        """Calculate load value at time t under harmonic loading.

        Formula: P(t) = P_0 * sin(omega * t)
        """
        omega = self.get_angular_frequency()
        return self.base_load_kn * math.sin(omega * t)

    def get_impulse_load_at_time(self, t: float, pulse_width_sec: float = 0.03) -> float:
        """Calculate load value at time t under impulse loading (haversine pulse).

        Formula: P(t) = P_0 * sin^2(pi * t / pulse_width) for 0 <= t <= pulse_width
        Reference: Huang, Y.H. (2004). Pavement Analysis and Design.
        """
        if 0.0 <= t <= pulse_width_sec:
            val = math.sin(math.pi * t / pulse_width_sec) ** 2
            return self.base_load_kn * val
        return 0.0
