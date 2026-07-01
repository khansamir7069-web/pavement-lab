"""Material Library module for managing versioned JSON material databases.

Provides abstract material interface, dynamic templates loading, custom presets,
registry lookups, and future expansion of material properties.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from mechanistic_solver.core.logging import get_logger

logger = get_logger("mechanistic_solver.materials")


class IMaterial(ABC):
    """Abstract base class representing dynamic material behavior models."""

    @abstractmethod
    def get_modulus(self) -> float:
        """Return the elastic modulus of the material in MPa."""
        pass

    @abstractmethod
    def get_poisson(self) -> float:
        """Return Poisson's ratio of the material."""
        pass

    @abstractmethod
    def temperature_adjust(self, temp_celsius: float) -> float:
        """Return the adjusted elastic modulus based on temperature in MPa."""
        pass

    @abstractmethod
    def frequency_adjust(self, freq_hz: float) -> float:
        """Return the adjusted elastic modulus based on loading frequency in MPa."""
        pass


class MaterialRecord(IMaterial):
    """Material record loaded from json templates implementing IMaterial."""
    
    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)
        
        # Core properties
        self.material_id: str = str(data["material_id"])
        self.material_name: str = str(data["material_name"])
        self.category: str = str(data["category"])
        self.layer_type: str = str(data["layer_type"])
        self.default_elastic_modulus_mpa: float = float(data["default_elastic_modulus_mpa"])
        self.recommended_modulus_min_mpa: float = float(data["recommended_modulus_min_mpa"])
        self.recommended_modulus_max_mpa: float = float(data["recommended_modulus_max_mpa"])
        self.poisson_ratio: float = float(data["poisson_ratio"])
        self.density_kg_m3: float = float(data["density_kg_m3"])
        
        # Metadata / environmental sensitivities
        self.temperature_sensitivity: str = str(data.get("temperature_sensitivity", "None"))
        self.moisture_sensitivity: str = str(data.get("moisture_sensitivity", "None"))
        self.drainage_rating: str = str(data.get("drainage_rating", "Fair"))
        self.expected_design_life_years: int = int(data.get("expected_design_life_years", 20))
        self.typical_irc_usage: str = str(data.get("typical_irc_usage", ""))
        self.engineering_notes: str = str(data.get("engineering_notes", ""))
        self.reference_source: str = str(data.get("reference_source", ""))
        self.version: str = str(data.get("version", "1.0.0"))
        self.revision: int = int(data.get("revision", 1))
        self.created_by: str = str(data.get("created_by", "System Admin"))
        self.last_updated: str = str(data.get("last_updated", ""))
        
        # Inactive AI Optimization placeholders (Phase 7)
        self.locked: bool = bool(data.get("locked", False))
        self.optimizable: bool = bool(data.get("optimizable", True))
        self.min_thickness_mm: float = float(data.get("min_thickness_mm", 0.0))
        self.max_thickness_mm: float = float(data.get("max_thickness_mm", 0.0))
        self.construction_cost_index: float = float(data.get("construction_cost_index", 0.0))
        self.carbon_footprint_index: float = float(data.get("carbon_footprint_index", 0.0))
        self.availability_rating: int = int(data.get("availability_rating", 10))
        self.material_priority: int = int(data.get("material_priority", 1))
        self.sustainability_score: int = int(data.get("sustainability_score", 50))

    def get_modulus(self) -> float:
        return self.default_elastic_modulus_mpa

    def get_poisson(self) -> float:
        return self.poisson_ratio

    def temperature_adjust(self, temp_celsius: float) -> float:
        # Placeholder temperature logic - returns default modulus
        return self.default_elastic_modulus_mpa

    def frequency_adjust(self, freq_hz: float) -> float:
        # Placeholder frequency logic - returns default modulus
        return self.default_elastic_modulus_mpa

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


class MaterialDatabase:
    """Manages loaded materials from a specific versioned database file."""
    
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.version = "1.0.0"
        self.database_name = ""
        self.materials: dict[str, MaterialRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.version = str(data.get("version", "1.0.0"))
            self.database_name = str(data.get("database_name", self.file_path.stem))
            
            for m_data in data.get("materials", []):
                rec = MaterialRecord(m_data)
                self.materials[rec.material_id] = rec
            logger.info("Loaded material database '%s' version %s", self.database_name, self.version)
        except Exception as e:
            logger.error("Failed to load material database from %s: %s", self.file_path, e)
            raise ValueError(f"Error loading database {self.file_path.name}: {e}") from e

    def get_material(self, material_id: str) -> MaterialRecord | None:
        return self.materials.get(material_id)


class MaterialLibrary:
    """Registry managing multiple versioned material databases."""
    
    def __init__(self, database_dir: Path | None = None) -> None:
        if database_dir is None:
            database_dir = Path(__file__).resolve().parent / "database"
        self.database_dir = database_dir
        self.databases: dict[str, MaterialDatabase] = {}
        self.default_db_key = "IRC37_2018"
        self.scan_and_load_all()

    def scan_and_load_all(self) -> None:
        """Scan database directory and load all JSON files."""
        if not self.database_dir.exists():
            self.database_dir.mkdir(parents=True, exist_ok=True)
            return
            
        for path in self.database_dir.glob("*.json"):
            key = path.stem
            try:
                db = MaterialDatabase(path)
                self.databases[key] = db
            except Exception as e:
                logger.warning("Skipping database file %s: %s", path.name, e)

    def get_database(self, key: str) -> MaterialDatabase | None:
        return self.databases.get(key)

    def get_material_from_db(self, db_key: str, material_id: str) -> MaterialRecord | None:
        db = self.get_database(db_key)
        if db:
            return db.get_material(material_id)
        return None

    def list_available_databases(self) -> list[str]:
        return sorted(list(self.databases.keys()))
