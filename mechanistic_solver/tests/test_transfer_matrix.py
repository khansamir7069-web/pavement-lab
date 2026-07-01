"""Unit tests for the transfer matrix builder and equations shape validation."""
from __future__ import annotations

import numpy as np
import pytest

from mechanistic_solver.core.models import Layer
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.matrix.transfer_matrix import TransferMatrixBuilder


def test_transfer_matrix_dimension_shapes() -> None:
    """Verify that coefficient matrix dimensions match the 4n-2 equation system exactly."""
    l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=50.0, poisson_ratio=0.4, density=1800.0)
    
    # 2-layer system (n=2): dim = 4(2)-2 = 6
    sys = LayerSystem(layers=(l1,), subgrade=sub)
    builder = TransferMatrixBuilder()
    coeff_sys = builder.build_for_layer_system(sys, 1.0)
    
    assert builder.validate_matrix_shapes(coeff_sys)
    assert coeff_sys.shape == (6, 6)
    assert len(coeff_sys.B) == 6
    
    # 3-layer system (n=3): dim = 4(3)-2 = 10
    l2 = Layer(name="WMM", thickness=150.0, elastic_modulus=300.0, poisson_ratio=0.35, density=2200.0)
    sys3 = LayerSystem(layers=(l1, l2), subgrade=sub)
    coeff_sys3 = builder.build_for_layer_system(sys3, 1.0)
    
    assert builder.validate_matrix_shapes(coeff_sys3)
    assert coeff_sys3.shape == (10, 10)
    
    # Check conditioning
    report = coeff_sys.check_conditioning()
    assert report.rank == 6
    assert not report.is_singular
