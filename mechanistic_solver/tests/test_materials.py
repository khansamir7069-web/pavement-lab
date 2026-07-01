"""Unit tests for the material library database and IMaterial interface."""
from __future__ import annotations

from pathlib import Path

from mechanistic_solver.materials.library import IMaterial, MaterialLibrary


def test_library_database_loading() -> None:
    """Verify that versioned material databases are loaded correctly."""
    lib = MaterialLibrary()
    dbs = lib.list_available_databases()
    assert "IRC37_2018" in dbs


def test_irc_2018_templates_and_interface() -> None:
    """Verify that loaded material records implement the IMaterial interface."""
    lib = MaterialLibrary()
    db = lib.get_database("IRC37_2018")
    assert db is not None
    
    # Check BC details
    bc = db.get_material("irc_bc")
    assert bc is not None
    assert bc.material_name == "Bituminous Concrete (BC)"
    
    # Verify it implements IMaterial
    assert isinstance(bc, IMaterial)
    assert bc.get_modulus() == 3000.0
    assert bc.get_poisson() == 0.35
    assert bc.temperature_adjust(40.0) == 3000.0
    assert bc.frequency_adjust(10.0) == 3000.0


def test_custom_and_latest_databases() -> None:
    """Verify custom databases load template properties."""
    lib = MaterialLibrary()
    
    db_custom = lib.get_database("Client_Custom")
    assert db_custom is not None
    cab = db_custom.get_material("custom_aggregate_base")
    assert cab is not None
    assert cab.get_modulus() == 280.0
