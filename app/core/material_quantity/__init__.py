"""Material Quantity Calculator — Phase 7.

Independent module: estimates layer-wise tonnage and binder demand for a
road stretch. Pure-Python; all formulas modular and source-tagged.
"""
from __future__ import annotations

from .layer_quantity import (
    REFERENCES,
    LAYER_TYPES,
    LayerInput,
    LayerResult,
    MaterialQuantityInput,
    MaterialQuantityResult,
    DEFAULT_DENSITY,
    DEFAULT_BINDER_PCT,
    DEFAULT_SPRAY_RATE_KGM2,
    compute_layer,
    compute_material_quantity,
)

__all__ = [
    "REFERENCES",
    "LAYER_TYPES",
    "LayerInput",
    "LayerResult",
    "MaterialQuantityInput",
    "MaterialQuantityResult",
    "DEFAULT_DENSITY",
    "DEFAULT_BINDER_PCT",
    "DEFAULT_SPRAY_RATE_KGM2",
    "compute_layer",
    "compute_material_quantity",
]
