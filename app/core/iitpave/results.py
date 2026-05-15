"""Phase-13 IITPAVE result containers.

Frozen, slotted dataclasses — same style as the rest of the project.
Numeric units:
    stress (sigma_*)   MPa
    strain (epsilon_*) micro-strain (1e-6 m/m)
    depth z, radius r  mm
The parser fills these from whichever runner produced the output text
(``StubRunner`` today, ``ExternalExeRunner`` once IITPAVE is bundled).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.core.code_refs import CodeRef


PLACEHOLDER_NOTE: str = (
    "Mechanistic stresses / strains in this result are PLACEHOLDER values "
    "produced by the in-process IITPAVE stub. Real IITPAVE 6.0 / IRC:37-2018 "
    "cl. 6.2 elastic-layer analysis is not bundled in V1; bundling lands "
    "with Phase 17."
)


@dataclass(frozen=True, slots=True)
class PointResult:
    """Stress + strain at one evaluation point.

    Sign convention follows IITPAVE: compressive stress positive,
    tensile strain positive (engineering convention used in IRC:37).
    """
    z_mm: float
    r_mm: float
    sigma_z_mpa: float
    sigma_r_mpa: float
    sigma_t_mpa: float
    epsilon_z_microstrain: float
    epsilon_r_microstrain: float
    epsilon_t_microstrain: float


@dataclass(frozen=True, slots=True)
class MechanisticResult:
    """Container produced by ``parse_iitpave_output``.

    ``source`` is one of ``"stub"`` / ``"external_exe"`` so consumers
    can decide whether to trust the numbers in calibration / report
    contexts. ``is_placeholder`` is True whenever the stub produced the
    underlying text.
    """
    point_results: Tuple[PointResult, ...]
    references: Tuple[CodeRef, ...]
    is_placeholder: bool = True
    source: str = "stub"
    notes: str = PLACEHOLDER_NOTE
