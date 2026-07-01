"""Unit tests for the new solver models, exceptions, and standalone validations."""
from __future__ import annotations

import math
import pytest

from mechanistic_solver.core.exceptions import (
    InvalidElasticModulusError,
    InvalidLayerConfigurationError,
    InvalidPoissonRatioError,
    NegativeThicknessError,
)
from mechanistic_solver.core.models import (
    Layer,
    ObservationPoint,
    Pavement,
    WheelLoad,
)
from mechanistic_solver.core.validation import (
    validate_density,
    validate_modulus,
    validate_poisson,
    validate_thickness,
)


def test_layer_valid_creation() -> None:
    """Verify that Layer parses correct inputs."""
    l = Layer(
        name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35,
        density=2400.0, temperature=35.0, nonlinear_flag=False,
        viscoelastic_flag=False, orthotropic_flag=False, drainage_flag=True
    )
    assert l.name == "BC"
    assert l.thickness == 40.0
    assert l.elastic_modulus == 3000.0
    assert l.poisson_ratio == 0.35
    assert l.density == 2400.0
    assert l.temperature == 35.0
    assert l.drainage_flag is True


def test_layer_invalid_modulus() -> None:
    """Verify invalid modulus values throw custom exceptions."""
    with pytest.raises(InvalidElasticModulusError, match="must be positive"):
        Layer(name="BC", thickness=40.0, elastic_modulus=0.0, poisson_ratio=0.35, density=2400.0)
        
    with pytest.raises(InvalidElasticModulusError, match="outside engineering limits"):
        Layer(name="BC", thickness=40.0, elastic_modulus=0.05, poisson_ratio=0.35, density=2400.0)


def test_layer_invalid_poisson() -> None:
    """Verify invalid Poisson's ratios throw custom exceptions."""
    with pytest.raises(InvalidPoissonRatioError, match="must be in the open range"):
        Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.0, density=2400.0)
        
    with pytest.raises(InvalidPoissonRatioError, match="must be in the open range"):
        Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.5, density=2400.0)


def test_layer_invalid_thickness() -> None:
    """Verify invalid thickness values throw custom exceptions."""
    with pytest.raises(NegativeThicknessError, match="must be positive"):
        Layer(name="BC", thickness=0.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
        
    with pytest.raises(NegativeThicknessError, match="outside realistic limits"):
        Layer(name="BC", thickness=0.5, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)


def test_pavement_valid_and_manipulation() -> None:
    """Test Pavement stack operations: add, edit, duplicate, remove, reorder."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    l2 = Layer(name="DBM", thickness=80.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    
    p = Pavement(layers=(l1,), subgrade=sub)
    assert len(p.layers) == 1
    
    # Add layer
    p = p.add_layer(l2, index=1)
    assert len(p.layers) == 2
    assert p.layers[1].name == "DBM"
    
    # Duplicate layer
    p = p.duplicate_layer(0)
    assert len(p.layers) == 3
    assert p.layers[1].name == "BC Copy"
    
    # Edit layer
    p = p.edit_layer(1, thickness=50.0)
    assert p.layers[1].thickness == 50.0
    
    # Move layer
    p = p.move_layer(1, 2)
    assert p.layers[2].name == "BC Copy"
    
    # Remove layer
    p = p.remove_layer(2)
    assert len(p.layers) == 2
    assert "BC Copy" not in [l.name for l in p.layers]


def test_pavement_invalid_configurations() -> None:
    """Verify invalid pavement structures throw custom exceptions."""
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    l1 = Layer(name="BC", thickness=None, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    
    with pytest.raises(InvalidLayerConfigurationError, match="cannot have infinite thickness"):
        Pavement(layers=(l1,), subgrade=sub)


def test_wheel_load_validation() -> None:
    """Verify wheel load limits check."""
    w = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)
    assert w.wheel_load == 40.0
    
    with pytest.raises(ValueError, match="Wheel load must be positive"):
        WheelLoad(wheel_load=-10.0, pressure=0.56, radius=150.0)


def test_observation_point_validation() -> None:
    """Verify observation point checks."""
    pt = ObservationPoint(x=0.0, y=0.0, z=100.0)
    assert pt.z == 100.0
    
    with pytest.raises(ValueError, match="Depth z must be non-negative"):
        ObservationPoint(x=0.0, y=0.0, z=-5.0)


def test_serialization() -> None:
    """Verify JSON serialization / deserialization roundtrip."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.35, density=1800.0)
    p = Pavement(layers=(l1,), subgrade=sub)
    
    serialized = p.to_dict()
    rehydrated = Pavement.from_dict(serialized)
    
    assert rehydrated.subgrade.name == "Subgrade"
    assert len(rehydrated.layers) == 1
    assert rehydrated.layers[0].name == "BC"
