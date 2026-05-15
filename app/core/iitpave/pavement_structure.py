"""Phase-13 pavement structure dataclasses for IITPAVE input.

Self-contained — does NOT import ``app.core.structural_design`` so the
integration layer stays independent. An adapter
:func:`from_structural_layers` bridges the Phase-4 ``StructuralResult``
composition when callers want to chain the two modules.

Units (consistent across the integration layer):
    thickness_mm        mm
    modulus_mpa         MPa
    load_kn             kN  (single wheel; axle = 2 x wheel)
    pressure_mpa        MPa
    spacing_mm          mm  (centre-to-centre dual wheels)
    z_mm, r_mm          mm  (radial point in cylindrical coords)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from app.core.code_refs import CodeRef


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:37-2018", "cl. 6.2",  "Multi-layered elastic analysis (IITPAVE)"),
    CodeRef("IRC:37-2018", "Annex F",  "Default Poisson's ratios for pavement layers"),
)


# ---------------------------------------------------------------------------
# Layer + structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PavementLayer:
    """One pavement layer for the elastic-layer analysis.

    A semi-infinite subgrade is represented with ``thickness_mm = None``;
    no layer above it may have ``thickness_mm = None``.
    """
    name: str
    material: str                 # tag, e.g. "BC", "DBM-II", "GSB", "Subgrade"
    modulus_mpa: float
    poisson_ratio: float = 0.35
    thickness_mm: float | None = None


@dataclass(frozen=True, slots=True)
class PavementStructure:
    """Ordered top-down stack of layers. Last entry must be the
    semi-infinite subgrade (thickness_mm == None)."""
    layers: Tuple[PavementLayer, ...]

    def __post_init__(self) -> None:
        if not self.layers:
            raise ValueError("PavementStructure requires at least one layer")
        if self.layers[-1].thickness_mm is not None:
            raise ValueError(
                "Last layer must be semi-infinite subgrade "
                "(thickness_mm = None)"
            )
        for layer in self.layers[:-1]:
            if layer.thickness_mm is None or layer.thickness_mm <= 0:
                raise ValueError(
                    f"Layer {layer.name!r} above subgrade must have a "
                    f"positive finite thickness"
                )

    @property
    def total_finite_thickness_mm(self) -> float:
        return sum(
            (layer.thickness_mm or 0.0) for layer in self.layers[:-1]
        )

    def bituminous_thickness_mm(self,
                                materials: Iterable[str] = ("BC", "DBM", "SMA")) -> float:
        """Sum of layer thicknesses whose ``material`` starts with any of
        ``materials`` (case-insensitive). Used by the default
        evaluation-point helper to find the bottom of the BT stack."""
        m_lower = tuple(s.lower() for s in materials)
        total = 0.0
        for layer in self.layers[:-1]:
            mat = (layer.material or "").lower()
            if any(mat.startswith(m) for m in m_lower):
                total += layer.thickness_mm or 0.0
        return total


# ---------------------------------------------------------------------------
# Load configuration (IRC:37-2018 cl. 6.2 dual-wheel default)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LoadConfig:
    """Wheel load + tire pressure + dual-wheel spacing.

    Defaults match the IRC:37-2018 cl. 6.2 standard dual-wheel
    configuration (single-wheel 20 kN of a 40 kN single-axle equivalent;
    contact pressure 0.56 MPa; c-c spacing 310 mm).
    """
    wheel_load_kn: float = 20.0
    tire_pressure_mpa: float = 0.56
    dual_wheel_spacing_mm: float = 310.0


# ---------------------------------------------------------------------------
# Evaluation points
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EvaluationPoint:
    """One (depth, radial-offset) probe for IITPAVE output."""
    z_mm: float
    r_mm: float = 0.0
    label: str = ""              # optional UI/report hint


def default_evaluation_points(
    structure: PavementStructure,
) -> Tuple[EvaluationPoint, ...]:
    """Two canonical points used by IRC:37-2018 mechanistic checks.

    * bottom of the bituminous-bound (BT) stack — fatigue probe
    * top of the subgrade — rutting probe
    """
    z_bt = structure.bituminous_thickness_mm()
    z_subgrade_top = structure.total_finite_thickness_mm
    return (
        EvaluationPoint(z_mm=z_bt, r_mm=0.0, label="bottom_of_BT"),
        EvaluationPoint(z_mm=z_subgrade_top, r_mm=0.0, label="top_of_subgrade"),
    )


# ---------------------------------------------------------------------------
# Adapter from Phase-4 structural composition
# ---------------------------------------------------------------------------

# Default Poisson's ratios from IRC:37-2018 Annex F. PLACEHOLDER values
# in the sense that engineer overrides should be honoured per project.
_DEFAULT_POISSON: dict[str, float] = {
    "BC":       0.35,
    "DBM":      0.35,
    "SMA":      0.35,
    "WMM":      0.35,
    "GSB":      0.35,
    "CTB":      0.25,
    "Subgrade": 0.40,
}


def _poisson_for(material: str) -> float:
    if not material:
        return 0.35
    m = material.upper()
    for tag, mu in _DEFAULT_POISSON.items():
        if m.startswith(tag.upper()):
            return mu
    return 0.35


def from_structural_layers(
    structural_layers: Iterable,
    *,
    subgrade_mr_mpa: float,
    subgrade_name: str = "Subgrade",
) -> PavementStructure:
    """Bridge a Phase-4 ``StructuralResult.composition`` (or any iterable
    of objects exposing ``name``, ``material``, ``thickness_mm`` and
    ``modulus_mpa``) into a Phase-13 ``PavementStructure``.

    A semi-infinite subgrade layer is appended automatically using
    ``subgrade_mr_mpa`` as its modulus.
    """
    layers: list[PavementLayer] = []
    for sl in structural_layers:
        material = getattr(sl, "material", "") or ""
        e_mpa = getattr(sl, "modulus_mpa", None)
        if e_mpa is None:
            # Conservative placeholder modulus when the source did not
            # supply one (e.g. older catalogue rows).
            e_mpa = 300.0
        layers.append(PavementLayer(
            name=getattr(sl, "name", "") or material or "layer",
            material=material,
            modulus_mpa=float(e_mpa),
            poisson_ratio=_poisson_for(material),
            thickness_mm=float(getattr(sl, "thickness_mm", 0.0) or 0.0),
        ))
    layers.append(PavementLayer(
        name=subgrade_name,
        material="Subgrade",
        modulus_mpa=float(subgrade_mr_mpa),
        poisson_ratio=_DEFAULT_POISSON["Subgrade"],
        thickness_mm=None,
    ))
    return PavementStructure(layers=tuple(layers))
