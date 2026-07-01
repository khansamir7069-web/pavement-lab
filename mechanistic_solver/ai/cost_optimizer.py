"""Cost optimization library representing material rates, haulage multipliers, and project cost sensitivity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# Default construction material unit rates per cubic meter (e.g. in INR or USD/m³)
DEFAULT_RATES: Mapping[str, float] = {
    "BC": 12000.0,
    "DBM": 10000.0,
    "WMM": 2500.0,
    "GSB": 1800.0,
    "SUBGRADE": 500.0
}


@dataclass(frozen=True)
class CostLibrary:
    """Stores construction unit rates and haulage multipliers."""
    unit_rates: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_RATES))
    haulage_multiplier: float = 1.0

    def get_rate(self, material_name: str) -> float:
        """Retrieve unit rate for material, falling back to a general default if unknown."""
        key = material_name.upper().strip()
        for name, rate in self.unit_rates.items():
            if name in key:
                return rate * self.haulage_multiplier
        return 2000.0 * self.haulage_multiplier  # general fallback rate


class CostOptimizer:
    """Calculates project construction costs, layer-wise costs, and cost sensitivities."""

    def __init__(self, cost_library: CostLibrary | None = None) -> None:
        self.library = cost_library or CostLibrary()

    def calculate_pavement_cost(
        self,
        layers: Sequence[Any],
        section_length_m: float = 1000.0,
        section_width_m: float = 7.0
    ) -> Mapping[str, Any]:
        """Compute the layer-wise volume and total estimated construction costs.

        Formula: Cost = sum( Thickness_i * Length * Width * Unit_Rate_i * Haulage )
        """
        area = section_length_m * section_width_m
        layer_costs = []
        total_cost = 0.0
        
        for i, layer in enumerate(layers):
            if layer.thickness is None:
                continue  # Skip infinite thickness subgrade
                
            thick_m = layer.thickness / 1000.0
            volume = thick_m * area
            rate = self.library.get_rate(layer.name)
            cost = volume * rate
            
            layer_costs.append({
                "layer_index": i,
                "layer_name": layer.name,
                "thickness_mm": layer.thickness,
                "volume_m3": volume,
                "unit_rate": rate,
                "cost": cost
            })
            total_cost += cost
            
        # Cost sensitivity (cost change per 1 mm change in thickness)
        sensitivity = []
        for i, layer in enumerate(layers):
            if layer.thickness is None:
                continue
            rate = self.library.get_rate(layer.name)
            # 1 mm = 0.001 m
            cost_per_mm = 0.001 * area * rate
            sensitivity.append({
                "layer_name": layer.name,
                "cost_sensitivity_per_mm": cost_per_mm
            })
            
        return {
            "section_length_m": section_length_m,
            "section_width_m": section_width_m,
            "section_area_m2": area,
            "total_project_cost": total_cost,
            "layer_wise_costs": layer_costs,
            "cost_sensitivity": sensitivity
        }
