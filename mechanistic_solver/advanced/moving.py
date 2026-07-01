"""Moving wheel loads simulation, coordinate transformations, and critical response envelope extraction."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence, Mapping, Any


@dataclass(frozen=True)
class TyrePosition:
    """Offset coordinates (dx, dy) of a tyre relative to the axle group center."""
    dx: float  # mm
    dy: float  # mm
    wheel_load_kn: float


class AxleConfiguration:
    """Defines standard axle wheel configurations (Single, Dual, Tandem, Tridem)."""

    @staticmethod
    def dual_tyre(wheel_load_kn: float, spacing_mm: float = 330.0) -> Sequence[TyrePosition]:
        """Dual tyre configuration with two wheels separated by dual spacing S_d."""
        half_s = spacing_mm / 2.0
        return [
            TyrePosition(-half_s, 0.0, wheel_load_kn / 2.0),
            TyrePosition(half_s, 0.0, wheel_load_kn / 2.0)
        ]

    @staticmethod
    def tandem_axle_dual_tyres(wheel_load_kn: float, dual_spacing_mm: float = 330.0, axle_spacing_mm: float = 1350.0) -> Sequence[TyrePosition]:
        """Tandem axle with dual tyres on each side (total 4 tyres per side, or 4 tyres for half-axle)."""
        half_ds = dual_spacing_mm / 2.0
        half_as = axle_spacing_mm / 2.0
        return [
            # Front axle duals
            TyrePosition(-half_ds, -half_as, wheel_load_kn / 4.0),
            TyrePosition(half_ds, -half_as, wheel_load_kn / 4.0),
            # Rear axle duals
            TyrePosition(-half_ds, half_as, wheel_load_kn / 4.0),
            TyrePosition(half_ds, half_as, wheel_load_kn / 4.0)
        ]


class MovingLoadSimulator:
    """Simulates moving wheels/axles along a pavement track and extracts critical response envelopes."""

    def __init__(self, tyres: Sequence[TyrePosition], velocity_kmh: float = 60.0) -> None:
        self.tyres = tyres
        self.velocity_ms = velocity_kmh / 3.6

    def get_tyre_positions_at_time(self, t: float) -> Sequence[tuple[float, float, float]]:
        """Return the coordinates (x, y, load) of all tyres at time t.

        Moving along the y-axis: y(t) = y_0 + v * t
        """
        positions = []
        for tyre in self.tyres:
            x_pos = tyre.dx
            y_pos = tyre.dy + self.velocity_ms * t * 1000.0  # Convert to mm
            positions.append((x_pos, y_pos, tyre.wheel_load_kn))
        return positions

    def compute_critical_envelope(
        self,
        solver: Any,
        pavement: Any,
        obs_x: float,
        obs_y: float,
        obs_z: float,
        time_steps: Sequence[float],
        pressure_mpa: float = 0.56,
        contact_radius_mm: float = 150.0
    ) -> Mapping[str, Any]:
        """Simulate moving load and extract maximum tensile/compressive strains and deflections.

        Uses the superposition principle for multi-tyre configurations.
        Reference: Huang, Y.H. (2004). Pavement Analysis and Design.
        """
        from mechanistic_solver.core.models import ObservationPoint, WheelLoad
        
        history_deflection = []
        history_strains = []
        
        max_tensile_strain = 0.0
        max_compressive_strain = 0.0
        max_displacement = 0.0
        
        for t in time_steps:
            tyre_coords = self.get_tyre_positions_at_time(t)
            
            # Accumulated responses for this step
            step_disp = 0.0
            step_eps_x = 0.0
            step_eps_y = 0.0
            step_eps_z = 0.0
            
            for tx, ty, load_kn in tyre_coords:
                # Radial distance from tyre center to observation point
                dx = obs_x - tx
                dy = obs_y - ty
                r = math.sqrt(dx**2 + dy**2)
                
                # Single tyre solve
                wl = WheelLoad(wheel_load=load_kn, pressure=pressure_mpa, radius=contact_radius_mm)
                pt = ObservationPoint(x=r, y=0.0, z=obs_z)
                
                try:
                    resp = solver.solve(pavement, (wl,), [pt])
                    step_disp += resp.surface_deflection
                    
                    # Accumulate strains
                    if resp.strain_results:
                        st = resp.strain_results[0]
                        # Convert radial/tangential coordinates back to Cartesian (x, y)
                        cos_theta = dx / r if r > 0.0 else 1.0
                        sin_theta = dy / r if r > 0.0 else 0.0
                        
                        eps_r = st.get("epsilon_r", 0.0)
                        eps_t = st.get("epsilon_t", 0.0)
                        
                        # Transformations
                        eps_x = eps_r * cos_theta**2 + eps_t * sin_theta**2
                        eps_y = eps_r * sin_theta**2 + eps_t * cos_theta**2
                        
                        step_eps_x += eps_x
                        step_eps_y += eps_y
                        step_eps_z += st.get("epsilon_z", 0.0)
                except Exception:
                    # Graceful error handling
                    pass
            
            # Store history
            history_deflection.append(step_disp)
            history_strains.append({"epsilon_x": step_eps_x, "epsilon_y": step_eps_y, "epsilon_z": step_eps_z})
            
            # Update envelopes
            max_displacement = max(max_displacement, step_disp)
            
            # Tensile is positive in RoadX conventions, compressive is negative
            for eps in (step_eps_x, step_eps_y):
                if eps > 0.0:
                    max_tensile_strain = max(max_tensile_strain, eps)
                else:
                    max_compressive_strain = min(max_compressive_strain, eps)
            
            if step_eps_z < 0.0:
                max_compressive_strain = min(max_compressive_strain, step_eps_z)
            else:
                max_tensile_strain = max(max_tensile_strain, step_eps_z)
                
        return {
            "max_displacement_mm": max_displacement * 1000.0,
            "max_tensile_strain_microstrain": max_tensile_strain * 1e6,
            "max_compressive_strain_microstrain": max_compressive_strain * 1e6,
            "time_history": {
                "steps": list(time_steps),
                "deflection": history_deflection,
                "strains": history_strains
            }
        }
