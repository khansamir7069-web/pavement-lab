"""Centralized unit conversion engine for flexible-pavement engineering.

Supports Length, Stress, Force, Pressure, Mass/Load, and Temperature units.
All conversion calculations use float64 (float) internally.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping

from mechanistic_solver.core.exceptions import UnitConversionError


class UnitCategory(Enum):
    LENGTH = "length"
    STRESS = "stress"
    FORCE = "force"
    PRESSURE = "pressure"
    MASS = "mass"
    TEMPERATURE = "temperature"


class Unit(Enum):
    # Lengths (Base: mm)
    MM = ("mm", UnitCategory.LENGTH, 1.0)
    CM = ("cm", UnitCategory.LENGTH, 10.0)
    M = ("m", UnitCategory.LENGTH, 1000.0)
    
    # Stress (Base: Pa)
    PA = ("Pa", UnitCategory.STRESS, 1.0)
    KPA = ("kPa", UnitCategory.STRESS, 1000.0)
    MPA = ("MPa", UnitCategory.STRESS, 1000000.0)
    
    # Force (Base: N)
    N = ("N", UnitCategory.FORCE, 1.0)
    KN = ("kN", UnitCategory.FORCE, 1000.0)
    
    # Pressure (Base: Pa)
    PA_P = ("Pa", UnitCategory.PRESSURE, 1.0)
    KPA_P = ("kPa", UnitCategory.PRESSURE, 1000.0)
    MPA_P = ("MPa", UnitCategory.PRESSURE, 1000000.0)
    KN_M2 = ("kN/m²", UnitCategory.PRESSURE, 1000.0)  # 1 kN/m² = 1 kPa = 1000 Pa
    
    # Mass (Base: kg)
    KG = ("kg", UnitCategory.MASS, 1.0)
    TON = ("ton", UnitCategory.MASS, 1000.0)
    
    # Temperature (Base: Celsius)
    CELSIUS = ("Celsius", UnitCategory.TEMPERATURE, 1.0)

    def __init__(self, symbol: str, category: UnitCategory, base_factor: float) -> None:
        self.symbol = symbol
        self.category = category
        self.base_factor = base_factor


def convert_value(value: float, from_unit: Unit, to_unit: Unit) -> float:
    """Convert an engineering value from one unit to another.

    Uses float64 precision internally.

    Args:
        value (float): Numerical value to convert.
        from_unit (Unit): Source unit.
        to_unit (Unit): Target unit.

    Returns:
        float: Converted value.

    Raises:
        UnitConversionError: If units belong to different, incompatible categories.
    """
    # Allow compatibility between stress and pressure categories
    is_stress_pressure = (
        from_unit.category in (UnitCategory.STRESS, UnitCategory.PRESSURE) and
        to_unit.category in (UnitCategory.STRESS, UnitCategory.PRESSURE)
    )
    
    if from_unit.category != to_unit.category and not is_stress_pressure:
        raise UnitConversionError(
            f"Cannot convert between incompatible unit categories: {from_unit.category.name} and {to_unit.category.name}"
        )
        
    if from_unit.category == UnitCategory.TEMPERATURE:
        # Standard conversion for Celsius is 1-to-1 if keeping Celsius base.
        # Future-proofing: if Kelvin is added, insert offset logic here.
        return float(value)
        
    value_in_base = float(value) * float(from_unit.base_factor)
    return float(value_in_base / to_unit.base_factor)


def parse_unit(symbol: str) -> Unit:
    """Resolve a string symbol name to its corresponding Unit Enum.

    Args:
        symbol (str): Symbol name (e.g. 'mm', 'MPa', 'Celsius').

    Returns:
        Unit: The matching Unit Enum.

    Raises:
        UnitConversionError: If symbol is unrecognized.
    """
    norm = symbol.strip()
    for u in Unit:
        if u.symbol == norm:
            return u
    raise UnitConversionError(f"Unrecognized unit symbol: '{symbol}'")
