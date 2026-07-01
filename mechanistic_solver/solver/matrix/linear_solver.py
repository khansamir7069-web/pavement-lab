"""Linear equations system solver for pavement transfer matrices.

Utilizes standard solve, least squares, and pseudo-inverse fallbacks,
raising custom exceptions if matrices are singular.
"""
from __future__ import annotations

import numpy as np
from mechanistic_solver.core.exceptions import SolverConvergenceError


def solve_system(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Solve the linear equation system A * x = B.

    Tries standard solve first, falls back to least squares and pseudo-inverse.

    Args:
        A: Coefficients matrix of shape (D, D).
        B: Right-hand side loading vector of shape (D,).

    Returns:
        np.ndarray: Solved coefficients vector.

    Raises:
        SolverConvergenceError: If the system is singular and cannot be solved.
    """
    if A.shape[0] != A.shape[1]:
        raise ValueError(f"System matrix A must be square. Got shape: {A.shape}.")
        
    cond = np.linalg.cond(A)
    # Check for singularity
    if np.isinf(cond) or cond > 1e16:
        # Check if rank is insufficient
        rank = np.linalg.matrix_rank(A)
        if rank < A.shape[0]:
            raise SolverConvergenceError(
                f"Boundary conditions matrix is singular. Rank={rank} < Dim={A.shape[0]}."
            )
            
    try:
        # 1. Standard exact solve
        return np.linalg.solve(A, B)
    except np.linalg.LinAlgError:
        try:
            # 2. Least squares fallback
            x, residuals, rank, s = np.linalg.lstsq(A, B, rcond=1e-15)
            if residuals.size > 0 and residuals[0] > 1e-3:
                raise SolverConvergenceError("Least squares solver failed to converge within tolerance.")
            return x
        except np.linalg.LinAlgError:
            try:
                # 3. Pseudo-inverse fallback
                pinv = np.linalg.pinv(A, rcond=1e-15)
                return np.dot(pinv, B)
            except Exception as e:
                raise SolverConvergenceError(f"Linear system solver failed entirely: {e}") from e
