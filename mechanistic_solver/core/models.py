"""Core data models representing the pavement layers and wheel load geometries.

All models utilize validation.py checks and custom exceptions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Sequence

from mechanistic_solver.core.exceptions import (
    InvalidElasticModulusError,
    InvalidLayerConfigurationError,
    InvalidPoissonRatioError,
    NegativeThicknessError,
)
from mechanistic_solver.core.validation import (
    validate_density,
    validate_modulus,
    validate_poisson,
    validate_thickness,
    validate_layer_stack,
)


@dataclass(frozen=True, slots=True)
class Layer:
    """Represents a single structural pavement layer with engineering properties."""
    name: str
    thickness: Optional[float]  # None indicates infinite thickness (subgrade)
    elastic_modulus: float      # in MPa
    poisson_ratio: float
    density: float              # in kg/m³
    temperature: Optional[float] = None
    nonlinear_flag: bool = False
    viscoelastic_flag: bool = False
    orthotropic_flag: bool = False
    drainage_flag: bool = False

    def __post_init__(self) -> None:
        """Enforce bounds validation on initialization."""
        if not self.name or not self.name.strip():
            raise InvalidLayerConfigurationError("Layer name cannot be empty.")
            
        if self.thickness is not None:
            validate_thickness(self.thickness, self.name)
            
        validate_modulus(self.elastic_modulus, self.name)
        validate_poisson(self.poisson_ratio, self.name)
        validate_density(self.density, self.name)

    def to_dict(self) -> dict[str, Any]:
        """Serialize layer to a dictionary."""
        return {
            "name": self.name,
            "thickness": self.thickness,
            "elastic_modulus": self.elastic_modulus,
            "poisson_ratio": self.poisson_ratio,
            "density": self.density,
            "temperature": self.temperature,
            "nonlinear_flag": self.nonlinear_flag,
            "viscoelastic_flag": self.viscoelastic_flag,
            "orthotropic_flag": self.orthotropic_flag,
            "drainage_flag": self.drainage_flag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layer:
        """Deserialize layer from a dictionary."""
        return cls(
            name=str(data["name"]),
            thickness=data["thickness"] if data["thickness"] is None else float(data["thickness"]),
            elastic_modulus=float(data["elastic_modulus"]),
            poisson_ratio=float(data["poisson_ratio"]),
            density=float(data["density"]),
            temperature=data.get("temperature") if data.get("temperature") is None else float(data.get("temperature")),
            nonlinear_flag=bool(data.get("nonlinear_flag", False)),
            viscoelastic_flag=bool(data.get("viscoelastic_flag", False)),
            orthotropic_flag=bool(data.get("orthotropic_flag", False)),
            drainage_flag=bool(data.get("drainage_flag", False)),
        )


@dataclass(frozen=True, slots=True)
class Pavement:
    """Represents a multi-layered pavement structure with stack manipulation methods."""
    layers: Sequence[Layer]
    subgrade: Layer
    surface: Optional[str] = None
    boundary: str = "full_friction"

    def __post_init__(self) -> None:
        """Validate pavement layers stack configuration."""
        validate_layer_stack(self.layers, self.subgrade)

    def add_layer(self, layer: Layer, index: int | None = None) -> Pavement:
        """Return a new Pavement instance with the layer inserted."""
        new_layers = list(self.layers)
        if index is None:
            new_layers.append(layer)
        else:
            new_layers.insert(index, layer)
        return Pavement(
            layers=tuple(new_layers),
            subgrade=self.subgrade,
            surface=self.surface,
            boundary=self.boundary
        )

    def remove_layer(self, index: int) -> Pavement:
        """Return a new Pavement instance with the layer at index removed."""
        if index < 0 or index >= len(self.layers):
            raise IndexError("Layer index out of range.")
        new_layers = list(self.layers)
        new_layers.pop(index)
        return Pavement(
            layers=tuple(new_layers),
            subgrade=self.subgrade,
            surface=self.surface,
            boundary=self.boundary
        )

    def edit_layer(self, index: int, **kwargs) -> Pavement:
        """Return a new Pavement instance with the layer edited."""
        if index < 0 or index >= len(self.layers):
            raise IndexError("Layer index out of range.")
        new_layers = list(self.layers)
        new_layers[index] = replace(new_layers[index], **kwargs)
        return Pavement(
            layers=tuple(new_layers),
            subgrade=self.subgrade,
            surface=self.surface,
            boundary=self.boundary
        )

    def duplicate_layer(self, index: int) -> Pavement:
        """Return a new Pavement instance with a duplicated layer suffix."""
        if index < 0 or index >= len(self.layers):
            raise IndexError("Layer index out of range.")
        source = self.layers[index]
        dup = replace(source, name=f"{source.name} Copy")
        
        new_layers = list(self.layers)
        new_layers.insert(index + 1, dup)
        return Pavement(
            layers=tuple(new_layers),
            subgrade=self.subgrade,
            surface=self.surface,
            boundary=self.boundary
        )

    def move_layer(self, from_index: int, to_index: int) -> Pavement:
        """Return a new Pavement instance with the layer reordered."""
        if from_index < 0 or from_index >= len(self.layers):
            raise IndexError("Source layer index out of range.")
        if to_index < 0 or to_index >= len(self.layers):
            raise IndexError("Target layer index out of range.")
        new_layers = list(self.layers)
        layer = new_layers.pop(from_index)
        new_layers.insert(to_index, layer)
        return Pavement(
            layers=tuple(new_layers),
            subgrade=self.subgrade,
            surface=self.surface,
            boundary=self.boundary
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pavement stack to a dict."""
        return {
            "layers": [l.to_dict() for l in self.layers],
            "subgrade": self.subgrade.to_dict(),
            "surface": self.surface,
            "boundary": self.boundary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pavement:
        """Deserialize a pavement stack from a dict."""
        return cls(
            layers=[Layer.from_dict(l) for l in data["layers"]],
            subgrade=Layer.from_dict(data["subgrade"]),
            surface=data.get("surface"),
            boundary=data.get("boundary", "full_friction"),
        )


@dataclass(frozen=True, slots=True)
class WheelLoad:
    """Represents a wheel contact load configuration."""
    wheel_load: float  # in kN
    pressure: float    # in MPa
    radius: float      # in mm
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        """Validate wheel load geometry values."""
        if self.wheel_load <= 0.0:
            raise ValueError(f"Wheel load must be positive. Got: {self.wheel_load} kN.")
        if self.pressure <= 0.0:
            raise ValueError(f"Pressure must be positive. Got: {self.pressure} MPa.")
        if self.radius <= 0.0:
            raise ValueError(f"Radius must be positive. Got: {self.radius} mm.")


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    """Represents coordinate location coordinates where output values are observed."""
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        if self.z < 0.0:
            raise ValueError(f"Depth z must be non-negative. Got: {self.z} mm.")
