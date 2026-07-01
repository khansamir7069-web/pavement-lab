"""Interface bonding and boundary condition specifications.

Defines the InterfaceCondition Enum (BONDED, UNBONDED, PARTIAL_BOND)
and the BoundaryConditionSet configuration manager.
"""
from __future__ import annotations

from enum import Enum
from typing import Sequence


class InterfaceCondition(Enum):
    BONDED = "bonded"
    UNBONDED = "unbonded"
    PARTIAL_BOND = "partial_bond"


class BoundaryConditionSet:
    """Stores and validates boundary/bonding conditions at layer interfaces."""

    def __init__(
        self,
        interface_conditions: Sequence[InterfaceCondition | str],
        bottom_base_condition: str = "infinite_halfspace"
    ) -> None:
        """Initialize the BoundaryConditionSet.

        Args:
            interface_conditions: Conditions at each interface (must be BONDED, UNBONDED, or PARTIAL_BOND).
            bottom_base_condition: Bottom boundary condition (e.g. "infinite_halfspace" or placeholder "rigid_base").
        """
        self.interface_conditions = [
            InterfaceCondition(c) if isinstance(c, str) else c for c in interface_conditions
        ]
        self.bottom_base_condition = bottom_base_condition
        self._validate()

    def _validate(self) -> None:
        """Enforce condition specifications and placeholders validation."""
        # Validate bottom base condition placeholder
        if self.bottom_base_condition not in ("infinite_halfspace", "rigid_base"):
            raise ValueError(f"Unrecognized bottom boundary condition: '{self.bottom_base_condition}'.")
            
        # Check for unsupported conditions
        for cond in self.interface_conditions:
            if cond != InterfaceCondition.BONDED:
                raise ValueError(
                    f"Interface condition '{cond.name}' is defined but only "
                    f"'BONDED' condition is supported in the current solver phase."
                )

    @classmethod
    def create_default(cls, num_interfaces: int) -> BoundaryConditionSet:
        """Create a boundary condition set with default BONDED conditions at all interfaces."""
        return cls(
            interface_conditions=[InterfaceCondition.BONDED] * num_interfaces,
            bottom_base_condition="infinite_halfspace"
        )
