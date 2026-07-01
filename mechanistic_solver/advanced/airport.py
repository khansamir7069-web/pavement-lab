"""Airport pavement aircraft gear configurations, landing gear wheel groups, and aircraft metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from mechanistic_solver.advanced.moving import TyrePosition


@dataclass(frozen=True)
class AircraftMetadata:
    """Metadata representing an aircraft and its standard operational loading parameters."""
    aircraft_name: str
    maximum_takeoff_weight_kg: float
    tyre_pressure_mpa: float
    main_gear_load_kn: float
    tyres_per_gear: int


# Modular database of standard commercial aircraft landing gears
AIRCRAFT_DATABASE: Mapping[str, AircraftMetadata] = {
    "B737-800": AircraftMetadata(
        aircraft_name="Boeing 737-800",
        maximum_takeoff_weight_kg=79000.0,
        tyre_pressure_mpa=1.40,
        main_gear_load_kn=360.0,
        tyres_per_gear=2
    ),
    "A320": AircraftMetadata(
        aircraft_name="Airbus A320",
        maximum_takeoff_weight_kg=78000.0,
        tyre_pressure_mpa=1.35,
        main_gear_load_kn=350.0,
        tyres_per_gear=2
    ),
    "B777-300ER": AircraftMetadata(
        aircraft_name="Boeing 777-300ER",
        maximum_takeoff_weight_kg=351000.0,
        tyre_pressure_mpa=1.50,
        main_gear_load_kn=1620.0,
        tyres_per_gear=6
    ),
    "B747-400": AircraftMetadata(
        aircraft_name="Boeing 747-400",
        maximum_takeoff_weight_kg=396000.0,
        tyre_pressure_mpa=1.45,
        main_gear_load_kn=900.0,
        tyres_per_gear=4
    )
}


class AirportGearFactory:
    """Generates layout positions and tyre offset configurations for commercial aircraft main gears."""

    @staticmethod
    def get_gear_tyres(aircraft_key: str) -> Sequence[TyrePosition]:
        """Retrieve tyre positions for a specific aircraft key.

        References: FAA Advisory Circular AC 150/5320-6G (Airport Pavement Design).
        """
        key = aircraft_key.upper().strip()
        if key not in AIRCRAFT_DATABASE:
            raise KeyError(f"Aircraft '{aircraft_key}' not found in modular database.")
            
        meta = AIRCRAFT_DATABASE[key]
        per_wheel_load = meta.main_gear_load_kn / meta.tyres_per_gear
        
        if "B737" in key or "A320" in key:
            # Dual wheel: spacing ~760 mm (30 inches)
            spacing = 760.0
            return [
                TyrePosition(-spacing / 2.0, 0.0, per_wheel_load),
                TyrePosition(spacing / 2.0, 0.0, per_wheel_load)
            ]
        elif "B747" in key:
            # Dual-Tandem: dual spacing ~1120 mm, tandem spacing ~1470 mm
            ds = 1120.0
            ts = 1470.0
            return [
                TyrePosition(-ds / 2.0, -ts / 2.0, per_wheel_load),
                TyrePosition(ds / 2.0, -ts / 2.0, per_wheel_load),
                TyrePosition(-ds / 2.0, ts / 2.0, per_wheel_load),
                TyrePosition(ds / 2.0, ts / 2.0, per_wheel_load)
            ]
        elif "B777" in key:
            # 6-wheel gear (tridem duals): dual spacing ~1400 mm, tandem spacing ~1450 mm
            ds = 1400.0
            ts = 1450.0
            return [
                # Front axle
                TyrePosition(-ds / 2.0, -ts, per_wheel_load),
                TyrePosition(ds / 2.0, -ts, per_wheel_load),
                # Middle axle
                TyrePosition(-ds / 2.0, 0.0, per_wheel_load),
                TyrePosition(ds / 2.0, 0.0, per_wheel_load),
                # Rear axle
                TyrePosition(-ds / 2.0, ts, per_wheel_load),
                TyrePosition(ds / 2.0, ts, per_wheel_load)
            ]
        else:
            # Default single wheel fallback
            return [TyrePosition(0.0, 0.0, meta.main_gear_load_kn)]
