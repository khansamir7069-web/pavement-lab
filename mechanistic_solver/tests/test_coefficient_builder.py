"""Unit tests for Burmister LayerCoefficients model representation."""
from __future__ import annotations

import pytest

from mechanistic_solver.solver.matrix.coefficient_builder import LayerCoefficients


def test_coefficient_builder_valid_creation() -> None:
    """Verify coefficient values initialization, indexing, and serialization."""
    c = LayerCoefficients(A=1.0, B=2.0, C=3.0, D=4.0, is_subgrade=False)
    assert c.A == 1.0
    assert c.B == 2.0
    assert c.C == 3.0
    assert c.D == 4.0
    assert c.is_subgrade is False
    
    # Indexing access
    assert c[0] == 1.0
    assert c[1] == 2.0
    assert c[2] == 3.0
    assert c[3] == 4.0
    
    with pytest.raises(IndexError):
        _ = c[4]


def test_coefficient_builder_subgrade_constraint() -> None:
    """Verify that subgrade coefficients enforce B and D as zero."""
    c_sub = LayerCoefficients(A=1.0, B=0.0, C=3.0, D=0.0, is_subgrade=True)
    assert c_sub.B == 0.0
    assert c_sub.D == 0.0
    
    # Initializing subgrade with positive B/D raises ValueError (enforced by builder init)
    with pytest.raises(ValueError, match="Subgrade coefficients B and D must be zero"):
        LayerCoefficients(A=1.0, B=2.0, C=3.0, D=0.0, is_subgrade=True)


def test_coefficient_builder_serialization() -> None:
    """Verify serialization and deserialization roundtrip."""
    c = LayerCoefficients(A=1.5, B=2.5, C=3.5, D=4.5, is_subgrade=False)
    serialized = c.to_dict()
    rehydrated = LayerCoefficients.from_dict(serialized)
    
    assert rehydrated.A == 1.5
    assert rehydrated.B == 2.5
    assert rehydrated.C == 3.5
    assert rehydrated.D == 4.5
    assert rehydrated.is_subgrade is False
