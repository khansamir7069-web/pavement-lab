"""Flexible Pavement Structural Design — IRC:37 skeleton (Phase 4).

Scope of this module (intentionally minimal):
  * Cumulative design traffic in MSA (IRC:37 Eq 3.1)
  * Subgrade resilient modulus from CBR (IRC:37 Eq 4.1 / 4.2)
  * Catalogue-style layer-thickness suggestion (placeholder)

Full mechanistic fatigue & rutting analysis (IITPAVE) is NOT included here;
fields are reserved so future phases can fill them in without breaking the
public dataclass shape.

Phase 15 P3 (additive): ``StructuralResult`` carries an optional
``mechanistic_validation`` reference so reports can render a real
``MechanisticValidationSummary`` (Phase 14) when one has been computed
for the project. The legacy ``fatigue_check`` / ``rutting_check`` string
fields stay as the fallback rendering path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

from .code_refs import CodeRef

if TYPE_CHECKING:
    # TYPE_CHECKING-only import keeps ``app.core.structural_design`` free
    # of a runtime dependency on the mechanistic-validation package
    # (preserves the existing import order in ``app.core.__init__``).
    from .mechanistic_validation import MechanisticValidationSummary
    from .intelligence_checker import IntelligenceResult

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:37-2018", "cl. 4.6",  "Cumulative design traffic (MSA)"),
    CodeRef("IRC:37-2018", "Annex E",  "Subgrade resilient modulus from CBR"),
    CodeRef("IRC:37-2018", "Plates 1-4", "Catalogue layer compositions"),
)

MECHANISTIC_WORKFLOW_NOT_RUN: str = (
    "IITPAVE unavailable - mechanistic workflow has not run. "
    "Use Structural Design Compute to run local IITPAVE or configure "
    "SAMPAVE_IITPAVE_EXE."
)


# ---------------------------------------------------------------------------
# Input / output dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StructuralInput:
    road_category: str = "NH / SH"
    design_life_years: int = 15
    initial_cvpd: float = 2000.0          # CVPD = commercial vehicles / day
    growth_rate_pct: float = 7.5          # annual %
    vdf: float = 2.5                       # Vehicle Damage Factor
    ldf: float = 0.75                      # Lane Distribution Factor
    subgrade_cbr_pct: float = 5.0          # 4-day soaked CBR (%)
    resilient_modulus_mpa: float | None = None   # optional measured Mr
    notes: str = ""

    def __post_init__(self) -> None:
        if self.initial_cvpd < 0:
            raise ValueError("CVPD must be >= 0")
        if self.growth_rate_pct < 0:
            raise ValueError("Growth rate must be >= 0")
        if self.design_life_years < 1:
            raise ValueError("Design life must be >= 1")
        if self.vdf < 0:
            raise ValueError("VDF must be >= 0")
        if self.ldf <= 0 or self.ldf > 1:
            raise ValueError("Lane distribution factor must be > 0 and <= 1")
        if self.subgrade_cbr_pct <= 0:
            raise ValueError("CBR must be > 0")


@dataclass(frozen=True, slots=True)
class PavementLayer:
    name: str                              # display name
    thickness_mm: float
    material: str = ""                     # tag (e.g. "BC", "DBM-II", "WMM")
    modulus_mpa: float | None = None       # typical / assumed E
    poisson: float | None = None

    def __post_init__(self) -> None:
        if self.thickness_mm <= 0:
            raise ValueError("Layer thickness must be > 0")
        if self.modulus_mpa is not None and self.modulus_mpa <= 0:
            raise ValueError("Modulus must be > 0")
        if self.poisson is not None and (self.poisson <= 0.05 or self.poisson >= 0.49):
            raise ValueError("Poisson's ratio must be physically realistic (between 0.05 and 0.49)")



@dataclass(frozen=True, slots=True)
class StructuralResult:
    inputs: StructuralInput
    design_msa: float
    growth_factor: float
    subgrade_mr_mpa: float
    composition: Tuple[PavementLayer, ...]
    total_pavement_thickness_mm: float
    fatigue_check: str = ""        # legacy string placeholder (Phase 4)
    rutting_check: str = ""        # legacy string placeholder (Phase 4)
    notes: str = ""
    # Phase 15 P3 — optional richer surface. When set, the structural
    # Word section renders the Phase-14 mechanistic helper instead of
    # the legacy string fields. Default None preserves Phase-4 behaviour
    # for every existing project.
    mechanistic_validation: "Optional[MechanisticValidationSummary]" = None
    intelligence: "Optional[IntelligenceResult]" = None
    validation_mode: str = "Decision Support Mode"


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

def compute_design_traffic(inp: StructuralInput) -> Tuple[float, float]:
    """Cumulative design traffic in MSA (IRC:37 Eq 3.1).

    N = 365 * A * [(1 + r)^n − 1] / r * D * F / 1e6   (r > 0)
    Returns ``(msa, growth_factor)``.
    """
    r = inp.growth_rate_pct / 100.0
    n = inp.design_life_years
    gf = ((1 + r) ** n - 1) / r if r > 0 else float(n)
    msa = 365.0 * inp.initial_cvpd * gf * inp.ldf * inp.vdf / 1_000_000.0
    return msa, gf


def compute_subgrade_mr(cbr_pct: float) -> float:
    """Subgrade resilient modulus from CBR (IRC:37).

    Mr_MPa = 10 × CBR              for CBR ≤ 5 %
           = 17.6 × CBR^0.64       otherwise
    """
    if cbr_pct <= 0:
        return 0.0
    if cbr_pct <= 5:
        return 10.0 * cbr_pct
    return 17.6 * (cbr_pct ** 0.64)


def suggest_composition(msa: float, cbr_pct: float) -> Tuple[PavementLayer, ...]:
    """Expose catalogue lookup composition (retains signature compatibility)."""
    from .catalogue.engine import lookup_catalogue_design
    return lookup_catalogue_design(msa, cbr_pct).composition


def compute_structural_design(inp: StructuralInput) -> StructuralResult:
    from .catalogue.engine import lookup_catalogue_design
    msa, gf = compute_design_traffic(inp)
    mr = (inp.resilient_modulus_mpa
          if inp.resilient_modulus_mpa
          else compute_subgrade_mr(inp.subgrade_cbr_pct))
    
    # Catalogue lookup
    cat_res = lookup_catalogue_design(msa, inp.subgrade_cbr_pct)
    comp = cat_res.composition
    total_t = sum(l.thickness_mm for l in comp)
    
    notes_list = []
    notes_list.append(cat_res.source_reference)
    for warn in cat_res.warnings:
        notes_list.append(warn)
        
    if inp.subgrade_cbr_pct > 20.0:
        notes_list.append("WARNING: Subgrade CBR is exceptionally high (> 20%). Verify field moisture conditions and subgrade compaction.")
        
    notes = " | ".join(notes_list)

    from .intelligence_checker import check_pavement_intelligence
    intel = check_pavement_intelligence(comp, mr)

    return StructuralResult(
        inputs=inp,
        design_msa=msa,
        growth_factor=gf,
        subgrade_mr_mpa=mr,
        composition=comp,
        total_pavement_thickness_mm=total_t,
        fatigue_check=MECHANISTIC_WORKFLOW_NOT_RUN,
        rutting_check=MECHANISTIC_WORKFLOW_NOT_RUN,
        notes=notes,
        intelligence=intel,
    )


