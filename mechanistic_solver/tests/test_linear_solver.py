"""Unit tests for the transfer matrix linear solver routines."""
from __future__ import annotations

import numpy as np
import pytest

from mechanistic_solver.core.exceptions import SolverConvergenceError
from mechanistic_solver.solver.matrix.linear_solver import solve_system


def test_linear_solver_accuracy() -> None:
    """Verify solve output for a standard well-conditioned system."""
    A = np.array([[2.0, 1.0], [1.0, 3.0]], dtype=np.float64)
    B = np.array([5.0, 5.0], dtype=np.float64)
    
    # 2x + y = 5; x + 3y = 5 -> x=2, y=1
    x = solve_system(A, B)
    assert np.allclose(x, np.array([2.0, 1.0]))


def test_linear_solver_singular_matrix() -> None:
    """Verify that singular matrices throw SolverConvergenceError."""
    A = np.array([[1.0, 2.0], [2.0, 4.0]], dtype=np.float64)  # Col 2 is 2x Col 1 (singular)
    B = np.array([5.0, 10.0], dtype=np.float64)
    
    with pytest.raises(SolverConvergenceError, match="singular"):
        solve_system(A, B)
