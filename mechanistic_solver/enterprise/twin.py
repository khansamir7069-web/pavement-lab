"""Digital Twin integration models for pavement sections featuring live sensor data and lifecycle states."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class SensorMetadata:
    """Represents a physical sensor installed inside a pavement layer."""
    sensor_id: str
    sensor_type: str  # strain_gauge, temperature_probe, geophone, moisture_meter
    depth_mm: float
    current_value: float
    unit: str


@dataclass
class DeteriorationState:
    """Represents calculated structural index parameters representing pavement degradation."""
    pavement_condition_index_pci: float  # 0 to 100
    structural_capacity_index: float     # 0.0 to 1.0 (modulus degradation)
    remaining_service_life_years: float


@dataclass
class DigitalTwinSection:
    """Represents a digital twin instance for a physical pavement section."""
    section_id: str
    lifecycle_state: str  # DESIGN, CONSTRUCTION, OPERATION, MAINTENANCE, RETIREMENT
    sensors: list[SensorMetadata] = field(default_factory=list)
    deterioration: DeteriorationState = field(default_factory=lambda: DeteriorationState(100.0, 1.0, 20.0))

    def update_sensor(self, sensor_id: str, value: float) -> None:
        """Update value for a registered sensor."""
        for s in self.sensors:
            if s.sensor_id == sensor_id:
                object.__setattr__(s, 'current_value', value)
                break

    def evaluate_maintenance_triggers(self) -> list[str]:
        """Check current deterioration indexes and suggest maintenance triggers."""
        triggers = []
        if self.deterioration.pavement_condition_index_pci < 70.0:
            triggers.append("Structural resurfacing overlay required (PCI < 70)")
        if self.deterioration.structural_capacity_index < 0.8:
            triggers.append("Base stabilization overlay or localized milling required")
        return triggers
