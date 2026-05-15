"""Phase-13 input-text generator.

Emits a plain-text representation of a ``PavementStructure`` + ``LoadConfig``
+ ``EvaluationPoint`` list. The exact column layout is *owned by us* via
the ``StubRunner`` contract today; it loosely follows the IITPAVE 6.0 /
IRC:37-2018 cl. 6.2 file conventions (number of layers, then one row per
layer, then load and evaluation points). Phase 17 will reconcile any
delta against the bundled exe.
"""
from __future__ import annotations

from typing import Iterable

from .pavement_structure import (
    EvaluationPoint,
    LoadConfig,
    PavementStructure,
)


INPUT_FORMAT_VERSION: str = "PHASE13_STUB_V1"


def build_iitpave_input(
    structure: PavementStructure,
    load: LoadConfig,
    points: Iterable[EvaluationPoint],
) -> str:
    """Return the canonical text representation consumed by ``IITPaveRunner``."""
    points = tuple(points)
    lines: list[str] = []
    lines.append(f"# pavement_lab iitpave input ({INPUT_FORMAT_VERSION})")
    lines.append(f"# {len(structure.layers)} layer(s); last layer = semi-infinite subgrade")
    lines.append(str(len(structure.layers)))
    for layer in structure.layers:
        # Subgrade thickness rendered as 0 (semi-infinite sentinel).
        h = 0.0 if layer.thickness_mm is None else float(layer.thickness_mm)
        lines.append(
            f"{layer.modulus_mpa:.4f} {layer.poisson_ratio:.4f} {h:.4f}"
        )
    lines.append(
        f"{load.wheel_load_kn:.4f} {load.tire_pressure_mpa:.4f} "
        f"{load.dual_wheel_spacing_mm:.4f}"
    )
    lines.append(str(len(points)))
    for pt in points:
        label = (pt.label or "").replace(" ", "_") or "-"
        lines.append(f"{pt.z_mm:.4f} {pt.r_mm:.4f} {label}")
    return "\n".join(lines) + "\n"
