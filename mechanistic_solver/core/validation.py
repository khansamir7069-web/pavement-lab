"""Reusable engineering validations decoupled from solver data models.

Imports constants and custom exceptions to validate layer thickness,
moduli, Poisson's ratios, densities, and layer stacks.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Sequence

from mechanistic_solver.core.constants import (
    MAX_DENSITY_KG_M3,
    MAX_MODULUS_MPA,
    MAX_POISSON_RATIO,
    MAX_THICKNESS_MM,
    MIN_DENSITY_KG_M3,
    MIN_MODULUS_MPA,
    MIN_POISSON_RATIO,
    MIN_THICKNESS_MM,
)
from mechanistic_solver.core.exceptions import (
    InvalidElasticModulusError,
    InvalidLayerConfigurationError,
    InvalidPoissonRatioError,
    NegativeThicknessError,
)

if TYPE_CHECKING:
    from mechanistic_solver.core.models import Layer


def validate_thickness(val: float, name: str = "Layer") -> None:
    """Validate that a finite layer thickness is positive and within range.

    Raises:
        NegativeThicknessError: If thickness is <= 0 or not finite.
    """
    if val <= 0.0 or math.isnan(val) or math.isinf(val):
        raise NegativeThicknessError(
            f"Thickness for '{name}' must be positive and finite. Got: {val} mm."
        )
    if val < MIN_THICKNESS_MM or val > MAX_THICKNESS_MM:
        raise NegativeThicknessError(
            f"Thickness for '{name}' ({val} mm) is outside realistic limits "
            f"[{MIN_THICKNESS_MM}, {MAX_THICKNESS_MM}] mm."
        )


def validate_modulus(val: float, name: str = "Layer") -> None:
    """Validate that elastic modulus is positive and within range.

    Raises:
        InvalidElasticModulusError: If modulus is <= 0 or out of bounds.
    """
    if val <= 0.0 or math.isnan(val) or math.isinf(val):
        raise InvalidElasticModulusError(
            f"Elastic Modulus for '{name}' must be positive and finite. Got: {val} MPa."
        )
    if val < MIN_MODULUS_MPA or val > MAX_MODULUS_MPA:
        raise InvalidElasticModulusError(
            f"Elastic Modulus for '{name}' ({val} MPa) is outside engineering limits "
            f"[{MIN_MODULUS_MPA}, {MAX_MODULUS_MPA}] MPa."
        )


def validate_poisson(val: float, name: str = "Layer") -> None:
    """Validate that Poisson's ratio is in the elastic range (0.0, 0.5).

    Raises:
        InvalidPoissonRatioError: If Poisson's ratio violates bounds.
    """
    if val <= MIN_POISSON_RATIO or val >= MAX_POISSON_RATIO or math.isnan(val):
        raise InvalidPoissonRatioError(
            f"Poisson's ratio for '{name}' must be in the open range "
            f"({MIN_POISSON_RATIO}, {MAX_POISSON_RATIO}). Got: {val}."
        )


def validate_density(val: float, name: str = "Layer") -> None:
    """Validate that density is positive and within bounds.

    Raises:
        ValueError: If density is out of range.
    """
    if val <= 0.0 or math.isnan(val) or math.isinf(val):
        raise ValueError(f"Density for '{name}' must be positive. Got: {val} kg/m³.")
    if val < MIN_DENSITY_KG_M3 or val > MAX_DENSITY_KG_M3:
        raise ValueError(
            f"Density for '{name}' ({val} kg/m³) is outside limits "
            f"[{MIN_DENSITY_KG_M3}, {MAX_DENSITY_KG_M3}] kg/m³."
        )


def validate_layer_stack(layers: Sequence[Layer], subgrade: Layer) -> None:
    """Validate structural ordering and constraints of the pavement layers stack.

    Raises:
        InvalidLayerConfigurationError: If the stack ordering is invalid.
    """
    if not layers:
        raise InvalidLayerConfigurationError("Pavement structure must contain at least one finite layer.")
        
    for i, layer in enumerate(layers):
        if layer.thickness is None:
            raise InvalidLayerConfigurationError(
                f"Intermediate layer '{layer.name}' (index {i}) cannot have infinite thickness."
            )
            
    if subgrade.thickness is not None:
        raise InvalidLayerConfigurationError(
            f"Subgrade layer '{subgrade.name}' must have infinite thickness (None)."
        )
