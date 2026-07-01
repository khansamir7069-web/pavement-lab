"""Solver coordinator engine implementation.

Supports both single-layer half-space calculations and the new multilayer
bonded interface solvers.
"""
from __future__ import annotations

import time
from typing import Sequence

from mechanistic_solver.core.exceptions import InvalidLayerConfigurationError
from mechanistic_solver.core.logging import get_logger
from mechanistic_solver.core.models import ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.outputs.response import Response
from mechanistic_solver.solver.displacement.displacement_solver import compute_halfspace_deflection
from mechanistic_solver.solver.displacement.multilayer_displacement_solver import compute_multilayer_displacement
from mechanistic_solver.solver.matrix.boundary_conditions import BoundaryConditionSet
from mechanistic_solver.solver.matrix.layer_system import LayerSystem
from mechanistic_solver.solver.strain.strain_solver import compute_halfspace_strain
from mechanistic_solver.solver.strain.multilayer_strain_solver import compute_multilayer_strain
from mechanistic_solver.solver.stress.stress_solver import compute_halfspace_stress
from mechanistic_solver.solver.stress.multilayer_stress_solver import compute_multilayer_stress

logger = get_logger("mechanistic_solver.solver")


class MechanisticSolver:
    """Coordinating engine for flexible-pavement calculations."""

    def __init__(self, mode: str = "halfspace") -> None:
        """Initialize the solver with a specific operational mode.

        Args:
            mode (str): Mode name. Must be "halfspace" or "multilayer".
        """
        if mode not in ("halfspace", "multilayer"):
            raise ValueError(
                f"Unsupported solver mode: '{mode}'. Supported: 'halfspace', 'multilayer'."
            )
        self.mode = mode

    def solve(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        observation_points: Sequence[ObservationPoint]
    ) -> Response:
        """Validate input parameters, run stress/strain/deflection kernels, and return Response.

        Args:
            pavement (Pavement): Layered pavement stack.
            loads (Sequence[WheelLoad]): Tire contact configuration list.
            observation_points (Sequence[ObservationPoint]): Coordinate points for analysis.

        Returns:
            Response: Standard response results container.
        """
        if self.mode == "halfspace":
            return self._solve_halfspace(pavement, loads, observation_points)
        else:
            return self._solve_multilayer(pavement, loads, observation_points)

    def _solve_halfspace(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        observation_points: Sequence[ObservationPoint]
    ) -> Response:
        """Run single-layer halfspace Boussinesq dispatches."""
        start_time = time.perf_counter()
        logger.info("Initializing halfspace solver execution.")

        if not loads:
            raise ValueError("At least one wheel load configuration is required.")
        if not observation_points:
            raise ValueError("At least one evaluation observation point is required.")

        if len(pavement.layers) > 1:
            raise InvalidLayerConfigurationError(
                f"Multilayer structure containing {len(pavement.layers)} layers is "
                f"unsupported in single-layer halfspace mode."
            )

        if len(pavement.layers) == 1:
            modulus = pavement.layers[0].elastic_modulus
            poisson = pavement.layers[0].poisson_ratio
        else:
            modulus = pavement.subgrade.elastic_modulus
            poisson = pavement.subgrade.poisson_ratio

        stress_list = []
        strain_list = []
        disp_list = []
        warnings_list = []

        for i, load in enumerate(loads):
            for j, point in enumerate(observation_points):
                stress = compute_halfspace_stress(load, point, modulus, poisson)
                stress_record = {"load_index": i, "point_index": j, **stress}
                stress_list.append(stress_record)

                strain = compute_halfspace_strain(stress, modulus, poisson)
                strain_record = {"load_index": i, "point_index": j, **strain}
                strain_list.append(strain_record)

                disp = compute_halfspace_deflection(load, point, modulus, poisson)
                if disp.get("warning"):
                    warnings_list.append(f"Load {i}, Point {j}: {disp['warning']}")
                disp_record = {"load_index": i, "point_index": j, **disp}
                disp_list.append(disp_record)

        # Centerline surface deflection: w0 = 2 * q * a * (1 - nu^2) / E
        first_load = loads[0]
        q_pa = float(first_load.pressure) * 1e6
        a_m = float(first_load.radius) / 1000.0
        E_pa = float(modulus) * 1e6
        surface_w = (2.0 * q_pa * a_m * (1.0 - poisson * poisson)) / E_pa

        duration = time.perf_counter() - start_time
        return Response(
            surface_deflection=surface_w,
            stress_results=stress_list,
            strain_results=strain_list,
            displacement_results=disp_list,
            runtime_seconds=duration,
            metadata={
                "solver_state": "halfspace_computed",
                "observation_points_count": len(observation_points),
                "wheel_loads_count": len(loads),
                "elastic_modulus_mpa": modulus,
                "poisson_ratio": poisson,
            },
            warnings=warnings_list,
            solver_version="1.0.0",
        )

    def _solve_multilayer(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        observation_points: Sequence[ObservationPoint]
    ) -> Response:
        """Run multilayer core solver dispatches."""
        from mechanistic_solver.licensing.license_manager import active_license
        from mechanistic_solver.licensing.features import FEATURE_MULTILAYER_SOLVER
        active_license.check_feature(FEATURE_MULTILAYER_SOLVER)
        
        start_time = time.perf_counter()
        logger.info("Initializing multilayer solver execution.")

        if not loads:
            raise ValueError("At least one wheel load configuration is required.")
        if not observation_points:
            raise ValueError("At least one evaluation observation point is required.")

        # Multilayer requires at least 1 finite layer and 1 subgrade (2 layers total)
        if len(pavement.layers) < 1:
            raise InvalidLayerConfigurationError(
                "Multilayer solver requires at least one finite layer and one subgrade."
            )

        # Build LayerSystem and default Bonded conditions
        layer_system = LayerSystem(pavement.layers, pavement.subgrade)
        boundary_conditions = BoundaryConditionSet.create_default(len(pavement.layers))

        stress_list = []
        strain_list = []
        disp_list = []
        warnings_list = []
        
        for i, load in enumerate(loads):
            for j, point in enumerate(observation_points):
                # Target layer containing depth z
                layer_idx = layer_system.get_layer_index_at_depth(point.z)
                target_layer = layer_system.subgrade if layer_idx == len(layer_system.layers) else layer_system.layers[layer_idx]
                
                # Stress
                stress = compute_multilayer_stress(layer_system, load, point, boundary_conditions)
                stress_record = {
                    "load_index": i,
                    "point_index": j,
                    **stress
                }
                stress_list.append(stress_record)
                for w in stress.get("warnings", []):
                    warnings_list.append(f"Load {i}, Point {j}: {w}")

                # Strain
                strain = compute_multilayer_strain(stress, target_layer)
                strain_record = {
                    "load_index": i,
                    "point_index": j,
                    **strain
                }
                strain_list.append(strain_record)
                for w in strain.get("warnings", []):
                    warnings_list.append(f"Load {i}, Point {j}: {w}")

                # Displacement
                disp = compute_multilayer_displacement(layer_system, load, point, boundary_conditions)
                disp_record = {
                    "load_index": i,
                    "point_index": j,
                    **disp
                }
                disp_list.append(disp_record)
                for w in disp.get("warnings", []):
                    warnings_list.append(f"Load {i}, Point {j}: {w}")

        # Compute centerline surface deflection (z=0, r=0) under first load
        surf_pt = ObservationPoint(x=0.0, y=0.0, z=0.0)
        first_load = loads[0]
        surf_disp = compute_multilayer_displacement(layer_system, first_load, surf_pt, boundary_conditions)
        surface_w = surf_disp.get("vertical_deflection")
        if surface_w is None:
            surface_w = 0.0

        duration = time.perf_counter() - start_time
        return Response(
            surface_deflection=surface_w,
            stress_results=stress_list,
            strain_results=strain_list,
            displacement_results=disp_list,
            runtime_seconds=duration,
            metadata={
                "solver_state": "multilayer_computed",
                "observation_points_count": len(observation_points),
                "wheel_loads_count": len(loads),
                "layers_count": len(layer_system.layers) + 1,
            },
            warnings=list(set(warnings_list)),
            solver_version="1.0.0",
            status="experimental",
            method_metadata={
                "boundary_base_condition": boundary_conditions.bottom_base_condition,
                "interface_condition": "bonded"
            }
        )
