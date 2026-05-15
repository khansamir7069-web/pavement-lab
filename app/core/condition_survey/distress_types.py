"""Distress-type registry, severity levels, and PCI deduct weights.

ALL WEIGHTS ARE PLACEHOLDERS. The shape mirrors ASTM D6433 (deduct-value
method) but the numeric weights are uncalibrated — they must be tuned
against an empirical pavement-distress dataset in a later phase.

A future calibration phase only needs to replace the active
``PCICalibration`` instance via ``set_calibration()``. All public names
(``SEVERITY_WEIGHTS``, ``DISTRESS_TYPES``, ``extent_factor``) read
through that single source of truth so callers never need to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Tuple


RECALIBRATE_ME: bool = True

PLACEHOLDER_NOTE: str = (
    "PCI weights, severity multipliers and rehab recommendations in this "
    "module are PLACEHOLDER values pending calibration against an "
    "empirical distress dataset (ASTM D6433 deduct-value curves and the "
    "IRC:82 maintenance treatment matrix). Scores below are indicative "
    "only — confirm against the relevant clause before adoption."
)


# ---------------------------------------------------------------------------
# Severity levels — uniform low / medium / high scale
# ---------------------------------------------------------------------------

SEVERITY_LEVELS: Tuple[str, ...] = ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Distress type registry
# ---------------------------------------------------------------------------

# Extent-unit aliases used by the engine
EXTENT_LENGTH = "length_m"
EXTENT_AREA   = "area_m2"
EXTENT_COUNT  = "count"


@dataclass(frozen=True, slots=True)
class DistressType:
    code: str             # e.g. "cracking"
    label: str            # e.g. "Cracking"
    extent_unit: str      # "length_m" | "area_m2" | "count"
    weight: float         # base deduct weight — PLACEHOLDER
    note: str = ""


# Base catalog of distress types — labels, units and notes are stable;
# the ``weight`` carried here is the PLACEHOLDER default, overridden via
# ``PCICalibration.distress_weights`` at module-active time.
_BASE_DISTRESS_CATALOG: Mapping[str, DistressType] = {
    "cracking": DistressType(
        code="cracking", label="Cracking",
        extent_unit=EXTENT_LENGTH, weight=1.2,
        note="Includes longitudinal, transverse, alligator and block cracking "
             "(ASTM D6433). Extent recorded as total crack length in metres "
             "per 100 m segment.",
    ),
    "rutting": DistressType(
        code="rutting", label="Rutting",
        extent_unit=EXTENT_AREA, weight=1.5,
        note="Permanent deformation in wheel path. Extent recorded as the "
             "affected surface area in m^2 (severity reflects rut depth).",
    ),
    "potholes": DistressType(
        code="potholes", label="Potholes",
        extent_unit=EXTENT_COUNT, weight=2.0,
        note="Bowl-shaped holes through the surface course. Extent recorded "
             "as number of potholes (severity reflects diameter/depth band).",
    ),
    "ravelling": DistressType(
        code="ravelling", label="Ravelling",
        extent_unit=EXTENT_AREA, weight=0.9,
        note="Progressive loss of surface aggregate. Extent recorded as the "
             "affected surface area in m^2.",
    ),
    "bleeding": DistressType(
        code="bleeding", label="Bleeding",
        extent_unit=EXTENT_AREA, weight=0.7,
        note="Excess binder rising to the surface in warm weather. Extent "
             "recorded as the affected surface area in m^2.",
    ),
    "patch_failures": DistressType(
        code="patch_failures", label="Patch Failures",
        extent_unit=EXTENT_AREA, weight=1.1,
        note="Failure of a previously placed patch (cracking, rutting, "
             "settlement of the patch). Extent in m^2.",
    ),
}


# ---------------------------------------------------------------------------
# Centralized PCI calibration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PCICalibration:
    """Single source of truth for every numeric constant the PCI engine uses.

    A future calibration phase only needs to construct a new
    ``PCICalibration`` and call :func:`set_calibration` — engine code,
    panels and reports continue to read through the same public names.
    """
    label: str                                          # human-readable tag
    severity_weights: Mapping[str, float]               # low/medium/high
    distress_weights: Mapping[str, float]               # by DistressType.code
    extent_divisor_length_m: float                      # m per length-unit
    extent_divisor_area_m2: float                       # m^2 per area-unit
    extent_divisor_count: float                         # count per unit (1.0 default)
    is_placeholder: bool = True


# Default calibration — every value flagged PLACEHOLDER.
DEFAULT_CALIBRATION = PCICalibration(
    label="ASTM D6433 — placeholder (uncalibrated)",
    severity_weights={"low": 1.0, "medium": 3.0, "high": 6.0},
    distress_weights={
        code: dt.weight for code, dt in _BASE_DISTRESS_CATALOG.items()
    },
    extent_divisor_length_m=100.0,
    extent_divisor_area_m2=10.0,
    extent_divisor_count=1.0,
    is_placeholder=True,
)


# Active calibration — mutable module-level cell, swapped by set_calibration().
_ACTIVE_CALIBRATION: PCICalibration = DEFAULT_CALIBRATION


def get_calibration() -> PCICalibration:
    """Return the currently active PCI calibration."""
    return _ACTIVE_CALIBRATION


def set_calibration(cal: PCICalibration) -> PCICalibration:
    """Install a new active calibration; returns the previous one.

    Public names ``SEVERITY_WEIGHTS`` and ``DISTRESS_TYPES`` are exposed
    as ``MappingProxy``-style views (re-built lazily on read via the
    module-level functions below) so engine code does not need to be
    rewired.
    """
    global _ACTIVE_CALIBRATION
    prev = _ACTIVE_CALIBRATION
    _ACTIVE_CALIBRATION = cal
    # Rebuild public-name views so existing imports of SEVERITY_WEIGHTS /
    # DISTRESS_TYPES see the new values without re-importing.
    _refresh_public_views()
    return prev


def reset_calibration() -> None:
    """Restore the placeholder default calibration."""
    set_calibration(DEFAULT_CALIBRATION)


# ---------------------------------------------------------------------------
# Public views (recomputed on calibration swap)
# ---------------------------------------------------------------------------

# These names are re-exported by ``app.core`` and read by engine.py. They
# are *recomputed in place* by _refresh_public_views() so that an
# ``from app.core import SEVERITY_WEIGHTS`` cached at import time keeps
# tracking the active calibration.
SEVERITY_WEIGHTS: dict = {}
DISTRESS_TYPES: dict = {}


def _refresh_public_views() -> None:
    cal = _ACTIVE_CALIBRATION
    SEVERITY_WEIGHTS.clear()
    SEVERITY_WEIGHTS.update(cal.severity_weights)
    DISTRESS_TYPES.clear()
    for code, base in _BASE_DISTRESS_CATALOG.items():
        w = cal.distress_weights.get(code, base.weight)
        DISTRESS_TYPES[code] = replace(base, weight=w)


_refresh_public_views()


def extent_factor(distress_code: str, length_m: float, area_m2: float,
                  count: int) -> float:
    """Return the dimensionless extent factor for a distress record.

    Reads the active ``PCICalibration``. PLACEHOLDER scaling (linear
    divide by 100 m / 10 m^2 / 1 count). Real ASTM D6433 uses log-curves;
    a calibrated replacement only needs to swap the calibration.
    """
    cal = _ACTIVE_CALIBRATION
    t = DISTRESS_TYPES.get(distress_code)
    if t is None:
        return 0.0
    if t.extent_unit == EXTENT_LENGTH:
        return max(0.0, length_m) / cal.extent_divisor_length_m
    if t.extent_unit == EXTENT_AREA:
        return max(0.0, area_m2) / cal.extent_divisor_area_m2
    if t.extent_unit == EXTENT_COUNT:
        return float(max(0, count)) / cal.extent_divisor_count
    return 0.0
