"""Maintenance / Rehabilitation engines — Phase 5 skeleton.

Three sub-modules:
  * overlay         — Benkelman Beam Deflection (BBD) overlay design (IRC:81).
  * cold_mix        — Cold bituminous mix proportioning (skeleton).
  * micro_surfacing — Type II / III micro-surfacing proportions (skeleton).

All three are intentionally conservative skeletons:
  * Pure Python, no external deps.
  * Frozen, slotted dataclasses for inputs / results — same style as Phase 4.
  * Results carry a ``notes`` field flagging the placeholder nature where
    relevant so the UI / future Word report can show it to the engineer.
"""
from __future__ import annotations

from .overlay import (
    OverlayInput,
    OverlayResult,
    compute_overlay,
    characteristic_deflection,
    allowable_deflection,
    temperature_corrected_deflection,
)
from .cold_mix import (
    ColdMixInput,
    ColdMixResult,
    compute_cold_mix,
)
from .micro_surfacing import (
    MicroSurfacingInput,
    MicroSurfacingResult,
    compute_micro_surfacing,
)

__all__ = [
    "OverlayInput",
    "OverlayResult",
    "compute_overlay",
    "characteristic_deflection",
    "allowable_deflection",
    "temperature_corrected_deflection",
    "ColdMixInput",
    "ColdMixResult",
    "compute_cold_mix",
    "MicroSurfacingInput",
    "MicroSurfacingResult",
    "compute_micro_surfacing",
]
