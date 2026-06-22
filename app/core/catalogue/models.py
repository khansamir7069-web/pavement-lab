from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
from app.core.structural_design import PavementLayer

@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    id: int
    cbr_min: float
    cbr_max: float
    msa_min: float
    msa_max: float
    reference_plate: str
    bituminous_thickness_mm: float
    granular_thickness_mm: float
    composition: Tuple[PavementLayer, ...]

@dataclass(frozen=True, slots=True)
class CatalogueLookupResult:
    composition: Tuple[PavementLayer, ...]
    source_reference: str
    warnings: Tuple[str, ...]
    is_out_of_range: bool
    is_boundary: bool
