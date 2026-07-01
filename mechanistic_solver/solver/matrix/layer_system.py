"""Layer system abstraction for multilayered pavements.

Maps evaluation depths to specific layers and tracks interface coordinate depths.
"""
from __future__ import annotations

from typing import Any, Sequence

from mechanistic_solver.core.models import Layer


class LayerSystem:
    """Manages cumulative depths and retrieves layers/interfaces at any depth."""

    def __init__(self, layers: Sequence[Layer], subgrade: Layer) -> None:
        """Initialize the LayerSystem.

        Args:
            layers: Sequence of finite thickness layers.
            subgrade: The infinite subgrade layer.
        """
        if subgrade.thickness is not None:
            raise ValueError("Subgrade layer must have infinite thickness (None).")
            
        for i, layer in enumerate(layers):
            if layer.thickness is None:
                raise ValueError(f"Finite layer '{layer.name}' (index {i}) cannot have infinite thickness.")
            if layer.thickness <= 0.0:
                raise ValueError(f"Finite layer '{layer.name}' must have positive thickness. Got: {layer.thickness}.")
                
        self.layers = list(layers)
        self.subgrade = subgrade
        self._build_depth_profile()

    def _build_depth_profile(self) -> None:
        """Calculate cumulative interface depths."""
        self._top_depths: list[float] = []
        self._bottom_depths: list[float | None] = []
        
        current_depth = 0.0
        for layer in self.layers:
            # We already validated layer.thickness is not None and > 0
            thickness = float(layer.thickness)
            self._top_depths.append(current_depth)
            current_depth += thickness
            self._bottom_depths.append(current_depth)
            
        # Add subgrade boundaries
        self._top_depths.append(current_depth)
        self._bottom_depths.append(None)  # Infinite bottom

    def get_layer_index_at_depth(self, z: float) -> int:
        """Retrieve the index of the layer containing depth z.

        Includes boundary [top, bottom) for finite layers.
        Subgrade index is equal to len(layers).
        """
        f_z = float(z)
        if f_z < 0.0:
            raise ValueError(f"Depth z must be non-negative. Got: {z} mm.")
            
        # Check finite layers
        for i in range(len(self.layers)):
            top = self._top_depths[i]
            bottom = self._bottom_depths[i]
            # If z falls exactly on the bottom interface, it belongs to the lower layer
            # except if it is the subgrade interface.
            if bottom is not None:
                if top <= f_z < bottom:
                    return i
                    
        # Otherwise it belongs to subgrade
        return len(self.layers)

    def get_layer_at_depth(self, z: float) -> Layer:
        """Retrieve the Layer object containing depth z."""
        idx = self.get_layer_index_at_depth(z)
        if idx == len(self.layers):
            return self.subgrade
        return self.layers[idx]

    def get_layer_top_depth(self, index: int) -> float:
        """Retrieve cumulative top depth of layer at index."""
        if index < 0 or index > len(self.layers):
            raise IndexError("Layer index out of range.")
        return self._top_depths[index]

    def get_layer_bottom_depth(self, index: int) -> float | None:
        """Retrieve cumulative bottom depth of layer at index."""
        if index < 0 or index > len(self.layers):
            raise IndexError("Layer index out of range.")
        return self._bottom_depths[index]

    def get_interface_depths(self) -> list[float]:
        """Return list of depths for all interfaces (excluding final infinity)."""
        # Interfaces are the bottom depths of all finite layers
        return [float(d) for d in self._bottom_depths[:-1]]

    def total_finite_thickness(self) -> float:
        """Sum of all finite layer thicknesses."""
        return sum(float(l.thickness) for l in self.layers)

    def to_dict(self) -> dict[str, Any]:
        """Serialize LayerSystem to a dictionary."""
        return {
            "layers": [l.to_dict() for l in self.layers],
            "subgrade": self.subgrade.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerSystem:
        """Deserialize LayerSystem from a dictionary."""
        return cls(
            layers=[Layer.from_dict(l) for l in data["layers"]],
            subgrade=Layer.from_dict(data["subgrade"]),
        )
