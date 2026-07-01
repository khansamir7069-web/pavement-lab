"""IRC:37 Pavement Design Engine orchestrating analysis, optimization, and reporting."""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.adequacy import check_structural_adequacy
from mechanistic_solver.design.optimization import optimize_bituminous_thickness
from mechanistic_solver.design.recommendations import RecommendationEngine
from mechanistic_solver.design.reporting import IRCDesignReportGenerator

# Name fragments that identify a bituminous-bound layer (case-insensitive).
# Kept consistent with the RoadX solver GUI bituminous-depth detection.
_BITUMINOUS_NAME_TAGS = ("bc", "dbm", "bm", "bituminous", "asphalt", "sma")


def _consecutive_bituminous_thickness_mm(layers: Sequence[Any]) -> float:
    """Sum the thickness of the consecutive bituminous layers from the surface.

    Walks the stack top-down and accumulates layer thickness while the layer
    name identifies a bituminous-bound course, stopping at the first granular
    or stabilised layer.  Returns 0.0 when the top layer is not bituminous.
    """
    total = 0.0
    for layer in layers:
        name = (getattr(layer, "name", "") or "").lower()
        if any(tag in name for tag in _BITUMINOUS_NAME_TAGS):
            total += float(layer.thickness or 0.0)
        else:
            break
    return total


class IRC37DesignEngine:
    """Design orchestrator executing structural evaluation, optimization, and reports."""

    def __init__(self, solver: MechanisticSolver | None = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")
        self.recommendation_engine = RecommendationEngine()
        self.report_generator = IRCDesignReportGenerator()

    def analyze(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        traffic_msa: float
    ) -> Mapping[str, Any]:
        """Perform structural adequacy check for a specific pavement configuration."""
        if not pavement.layers:
            raise ValueError("Pavement must contain at least one layer.")
            
        warnings: list[str] = []

        # 1. Setup observation depths.
        #    The fatigue-critical tensile strain acts at the bottom of the full
        #    bituminous-bound stack (consecutive top BC + DBM + asphalt/SMA/BM
        #    layers), not merely the first layer.  This matches the RoadX solver
        #    GUI's bituminous-depth probe.
        bituminous_depth = _consecutive_bituminous_thickness_mm(pavement.layers)
        h1 = bituminous_depth if bituminous_depth > 0.0 else float(pavement.layers[0].thickness)
        subgrade_depth = sum(float(l.thickness) for l in pavement.layers)

        points = [
            ObservationPoint(0.0, 0.0, h1),
            ObservationPoint(0.0, 0.0, subgrade_depth)
        ]

        # 2. Run solver
        response = self.solver.solve(pavement, loads, points)
        solver_status = response.status

        # 3. Extract critical strains.  The solver works in a compression-positive
        #    convention, so the horizontal tensile strain at the bottom of the
        #    bituminous layer and the vertical compressive strain at the subgrade
        #    top are taken as magnitudes for the IRC:37 fatigue/rutting models
        #    (both models are defined on the strain magnitude).
        strain_0 = response.strain_results[0]
        eps_r0 = strain_0.get("epsilon_r") or 0.0
        eps_t0 = strain_0.get("epsilon_t") or 0.0
        eps_t = max(abs(eps_r0), abs(eps_t0))

        strain_1 = response.strain_results[1]
        eps_v = abs(strain_1.get("epsilon_z") or 0.0)

        # Convert to microstrain for reporting convenience
        eps_t_micro = eps_t * 1e6
        eps_v_micro = eps_v * 1e6
        
        # 4. Check structural adequacy
        e_bc_mpa = float(pavement.layers[0].elastic_modulus)
        adequacy = check_structural_adequacy(
            eps_t, e_bc_mpa, eps_v, traffic_msa, warnings=warnings
        )
        
        # Include raw critical responses
        result = dict(adequacy)
        result["critical_strains"] = {
            "epsilon_t": eps_t,
            "epsilon_t_microstrain": eps_t_micro,
            "epsilon_v": eps_v,
            "epsilon_v_microstrain": eps_v_micro
        }
        result["solver_status"] = solver_status
        
        return result

    def design_and_optimize(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        traffic_msa: float,
        output_dir: str | None = None,
        min_thickness_mm: float = 40.0,
        max_thickness_mm: float = 300.0,
        step_mm: float = 5.0,
        max_iterations: int = 30
    ) -> Mapping[str, Any]:
        """Optimize layer thicknesses, generate recommendations, and output reports."""
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "reports", "design"
            )
            
        from mechanistic_solver.core.profiler import global_profiler
        from mechanistic_solver.core.cache import global_cache
        
        global_profiler.start()
        global_profiler.batch_count = 1
        
        try:
            # 1. Run optimization
            opt_res = optimize_bituminous_thickness(
                pavement, loads, traffic_msa,
                min_thickness_mm=min_thickness_mm,
                max_thickness_mm=max_thickness_mm,
                step_mm=step_mm,
                max_iterations=max_iterations
            )
            
            opt_pavement = opt_res["optimized_pavement"]
            
            # 2. Analyze the final optimized configuration
            final_adequacy = self.analyze(opt_pavement, loads, traffic_msa)
            
            # 3. Generate recommendations
            recs = self.recommendation_engine.generate_recommendations(
                opt_pavement, final_adequacy, solver_status=final_adequacy["solver_status"]
            )
            
            # 4. Save reports
            md_path, json_path = self.report_generator.save_reports(
                opt_pavement, loads, traffic_msa, final_adequacy,
                opt_res, recs, final_adequacy["solver_status"], output_dir
            )
        finally:
            global_profiler.stop()
            perf_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "reports", "performance"
            )
            global_profiler.save_reports(global_cache.get_statistics(), num_workers=1, output_dir=perf_dir)
            
        return {
            "optimized_pavement": opt_pavement,
            "adequacy": final_adequacy,
            "optimization": opt_res,
            "recommendations": recs,
            "report_paths": {
                "markdown": md_path,
                "json": json_path
            }
        }
DefinitionOfDone = True
