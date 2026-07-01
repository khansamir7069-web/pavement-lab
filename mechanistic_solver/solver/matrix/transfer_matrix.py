"""Transfer matrix mathematical structures and equations builder.

Assembles boundary conditions and bonded interface coefficients matrices
for multilayer elastic analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.matrix.boundary_equations import assemble_bonded_system


@dataclass(frozen=True)
class MatrixConditionReport:
    """Report summarizing numerical stability parameters of assembled system matrices."""
    condition_number: float
    is_singular: bool
    rank: int
    determinant: float
    status: str  # "computed" | "incomplete" | "singular"


class LayerCoefficientSystem:
    """Container for the assembled coefficient matrix A and boundary vector B."""

    def __init__(self, A: np.ndarray, B: np.ndarray, num_layers: int) -> None:
        """Initialize the LayerCoefficientSystem.

        Args:
            A: Coefficient matrix of shape (4n-2, 4n-2)
            B: Boundary vector of shape (4n-2,)
            num_layers: Number of layers in the system.
        """
        self.A = A
        self.B = B
        self.num_layers = num_layers
        self.shape = A.shape

    def check_conditioning(self) -> MatrixConditionReport:
        """Evaluate rank, determinant, and condition number of the system matrix A."""
        try:
            cond = float(np.linalg.cond(self.A))
            rank = int(np.linalg.matrix_rank(self.A))
            det = float(np.linalg.det(self.A))
            is_sing = (cond > 1e15) or (rank < self.shape[0])
            status = "singular" if is_sing else "computed"
            return MatrixConditionReport(
                condition_number=cond,
                is_singular=is_sing,
                rank=rank,
                determinant=det,
                status=status
            )
        except Exception:
            return MatrixConditionReport(
                condition_number=float("nan"),
                is_singular=True,
                rank=0,
                determinant=0.0,
                status="incomplete"
            )


class TransferMatrixBuilder:
    """Assembles transfer matrix and interface continuity equations."""

    def build_for_layer_system(
        self,
        layer_system: LayerSystem,
        radial_parameter: float,
        wheel_load_radius_m: float = 0.15,
        contact_pressure_pa: float = 560000.0
    ) -> LayerCoefficientSystem:
        """Assemble the linear system coefficient matrix A and vector B.

        Assembles equations representing bonded interfaces of shape (4n-2, 4n-2).
        """
        from mechanistic_solver.core.profiler import global_profiler
        with global_profiler.measure("transfer_matrix"):
            A, B = assemble_bonded_system(
                layer_system,
                radial_parameter,
                wheel_load_radius_m,
                contact_pressure_pa
            )
            return LayerCoefficientSystem(A, B, len(layer_system.layers) + 1)

    def validate_matrix_shapes(self, system: LayerCoefficientSystem) -> bool:
        """Confirm system dimensions match the 4n-2 requirement."""
        n = system.num_layers
        expected_dim = 4 * n - 2
        return system.shape == (expected_dim, expected_dim) and len(system.B) == expected_dim
