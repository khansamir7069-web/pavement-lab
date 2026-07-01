"""Burmister unknown coefficients representation for layered pavement systems.

Encapsulates A, B, C, D coefficients for finite layers and A, C for subgrade.
"""
from __future__ import annotations

from typing import Any


class LayerCoefficients:
    """Stores the unknown integration constants for a single pavement layer."""

    def __init__(
        self,
        A: float = 0.0,
        B: float = 0.0,
        C: float = 0.0,
        D: float = 0.0,
        is_subgrade: bool = False
    ) -> None:
        """Initialize the LayerCoefficients.

        Args:
            A: Coefficient A (downward exponential factor)
            B: Coefficient B (upward exponential factor, 0 for subgrade)
            C: Coefficient C (downward linear-exponential factor)
            D: Coefficient D (upward linear-exponential factor, 0 for subgrade)
            is_subgrade: Flag indicating if this is the infinite subgrade.
        """
        if is_subgrade and (B != 0.0 or D != 0.0):
            raise ValueError("Subgrade coefficients B and D must be zero.")
        self.A = float(A)
        self.B = 0.0 if is_subgrade else float(B)
        self.C = float(C)
        self.D = 0.0 if is_subgrade else float(D)
        self.is_subgrade = is_subgrade

    def __getitem__(self, index: int) -> float:
        """Retrieve coefficients by index (0: A, 1: B, 2: C, 3: D)."""
        if index == 0:
            return self.A
        elif index == 1:
            return self.B
        elif index == 2:
            return self.C
        elif index == 3:
            return self.D
        else:
            raise IndexError("Coefficient index must be between 0 and 3.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize coefficients to a dict."""
        return {
            "A": self.A,
            "B": self.B,
            "C": self.C,
            "D": self.D,
            "is_subgrade": self.is_subgrade
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerCoefficients:
        """Deserialize coefficients from a dict."""
        return cls(
            A=data["A"],
            B=data["B"],
            C=data["C"],
            D=data["D"],
            is_subgrade=data.get("is_subgrade", False)
        )
