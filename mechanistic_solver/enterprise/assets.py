"""Pavement Asset Management inventory models (roads, sections, condition records, maintenance logs)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class ConditionRecord:
    """Represents a measured pavement surface condition record."""
    timestamp: str
    rutting_depth_mm: float
    crack_area_pct: float
    deflection_mm: float
    roughness_iri: float


@dataclass
class MaintenanceActivity:
    """Represents an executed maintenance or rehabilitation action."""
    timestamp: str
    activity_type: str  # overlay, milling, reconstruction, pothole_patching
    cost: float
    thickness_mm: float = 0.0


@dataclass
class RoadSection:
    """Represents a discrete segment of a road corridor."""
    section_id: str
    name: str
    start_chainage: float
    end_chainage: float
    layers: Sequence[Any]
    subgrade: Any
    condition_history: list[ConditionRecord] = field(default_factory=list)
    maintenance_history: list[MaintenanceActivity] = field(default_factory=list)

    def add_condition(self, record: ConditionRecord) -> None:
        """Append a condition monitoring record."""
        self.condition_history.append(record)

    def add_maintenance(self, activity: MaintenanceActivity) -> None:
        """Append a maintenance record."""
        self.maintenance_history.append(activity)


@dataclass
class PavementAsset:
    """Represents an entire road asset corridor containing multiple sections."""
    road_id: str
    name: str
    length_km: float
    sections: list[RoadSection] = field(default_factory=list)

    def add_section(self, section: RoadSection) -> None:
        """Append a road section to this corridor."""
        self.sections.append(section)
