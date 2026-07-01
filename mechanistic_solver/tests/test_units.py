"""Unit tests for the centralized unit conversion engine."""
from __future__ import annotations

import pytest

from mechanistic_solver.core.exceptions import UnitConversionError
from mechanistic_solver.core.units import Unit, convert_value, parse_unit


def test_unit_parsing() -> None:
    """Verify that unit symbols resolve correctly."""
    assert parse_unit("mm") == Unit.MM
    assert parse_unit("cm") == Unit.CM
    assert parse_unit("m") == Unit.M
    assert parse_unit("Pa") == Unit.PA
    assert parse_unit("kPa") == Unit.KPA
    assert parse_unit("MPa") == Unit.MPA
    assert parse_unit("kN/m²") == Unit.KN_M2
    assert parse_unit("kN") == Unit.KN
    assert parse_unit("kg") == Unit.KG
    assert parse_unit("ton") == Unit.TON
    assert parse_unit("Celsius") == Unit.CELSIUS
    
    with pytest.raises(UnitConversionError, match="Unrecognized unit symbol"):
        parse_unit("invalid_unit")


def test_length_conversions() -> None:
    """Verify that length units convert correctly."""
    assert convert_value(10.0, Unit.CM, Unit.MM) == 100.0
    assert convert_value(1.0, Unit.M, Unit.CM) == 100.0
    assert convert_value(250.0, Unit.MM, Unit.M) == 0.25


def test_stress_conversions() -> None:
    """Verify that stress and pressure units convert correctly."""
    assert convert_value(1.0, Unit.MPA, Unit.KPA) == 1000.0
    assert convert_value(100.0, Unit.KPA, Unit.KN_M2) == 100.0  # 1 kPa = 1 kN/m2
    assert convert_value(1000.0, Unit.PA, Unit.KPA) == 1.0


def test_mass_conversions() -> None:
    """Verify mass/load conversions."""
    assert convert_value(2.0, Unit.TON, Unit.KG) == 2000.0
    assert convert_value(1500.0, Unit.KG, Unit.TON) == 1.5


def test_temperature_conversions() -> None:
    """Verify Celsius unit adjustment."""
    assert convert_value(35.0, Unit.CELSIUS, Unit.CELSIUS) == 35.0


def test_incompatible_conversions() -> None:
    """Verify that attempting to convert incompatible categories raises UnitConversionError."""
    with pytest.raises(UnitConversionError, match="Cannot convert between incompatible unit categories"):
        convert_value(40.0, Unit.MM, Unit.KN)
        
    with pytest.raises(UnitConversionError, match="Cannot convert between incompatible unit categories"):
        convert_value(100.0, Unit.MPA, Unit.TON)
