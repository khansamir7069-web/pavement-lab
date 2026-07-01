"""Enterprise Service API layer wrapping solver, optimizer, design, and AI recommendation engines."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Layer, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.irc37_engine import IRC37DesignEngine
from mechanistic_solver.ai.cost_optimizer import CostOptimizer
from mechanistic_solver.ai.layer_optimizer import LayerOptimizer
from mechanistic_solver.ai.recommendations import AIRecommendationEngine


class EnterpriseServiceAPI:
    """Consolidated business-logic service API for the RoadX ecosystem."""

    def __init__(self, solver: Any = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")
        self.design_engine = IRC37DesignEngine(solver=self.solver)
        self.cost_opt = CostOptimizer()
        self.layer_opt = LayerOptimizer(solver=self.solver)
        self.recs_engine = AIRecommendationEngine()

    def create_pavement_project(
        self,
        layers_data: Sequence[Mapping[str, Any]],
        subgrade_data: Mapping[str, Any]
    ) -> Pavement:
        """Create a validated Pavement project instance."""
        layers = []
        for l in layers_data:
            layers.append(Layer(
                name=l["name"],
                thickness=l["thickness"],
                elastic_modulus=l["elastic_modulus"],
                poisson_ratio=l.get("poisson_ratio", 0.35),
                density=l.get("density", 2400.0)
            ))
        subgrade = Layer(
            name=subgrade_data["name"],
            thickness=None,
            elastic_modulus=subgrade_data["elastic_modulus"],
            poisson_ratio=subgrade_data.get("poisson_ratio", 0.40),
            density=subgrade_data.get("density", 1800.0)
        )
        return Pavement(layers=tuple(layers), subgrade=subgrade)

    def execute_solver_run(
        self,
        pavement: Pavement,
        loads_data: Sequence[Mapping[str, Any]],
        points_data: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Run the deterministic mechanistic solver and return structured responses."""
        from mechanistic_solver.core.models import ObservationPoint
        loads = [WheelLoad(wheel_load=l["wheel_load"], pressure=l["pressure"], radius=l["radius"]) for l in loads_data]
        points = [ObservationPoint(x=p["x"], y=p["y"], z=p["z"]) for p in points_data]
        
        resp = self.solver.solve(pavement, tuple(loads), points)
        return {
            "deflection_mm": resp.surface_deflection,
            "stresses": resp.stress_results,
            "strains": resp.strain_results,
            "warnings": resp.warnings
        }

    def run_ai_optimization(
        self,
        pavement: Pavement,
        load_data: Mapping[str, Any],
        design_traffic_msa: float,
        bounds: Mapping[str, tuple[float, float]]
    ) -> dict[str, Any]:
        """Execute automated layer optimization, cost calculations, and suggestions."""
        load = WheelLoad(wheel_load=load_data["wheel_load"], pressure=load_data["pressure"], radius=load_data["radius"])
        opt_res = self.layer_opt.optimize_layers(pavement, (load,), design_traffic_msa, bounds)
        
        # Calculate costs for the best pavement
        opt_pav = opt_res["optimal_pavement"]
        cost_res = self.cost_opt.calculate_pavement_cost(opt_pav.layers)
        
        # Get structural adequacy for recommendations
        # Build observation points
        h1 = float(opt_pav.layers[0].thickness) if opt_pav.layers else 150.0
        subgrade_depth = sum(float(l.thickness) for l in opt_pav.layers if l.thickness is not None)
        from mechanistic_solver.core.models import ObservationPoint
        pts = [
            ObservationPoint(x=0.0, y=0.0, z=h1),
            ObservationPoint(x=0.0, y=0.0, z=subgrade_depth)
        ]
        
        resp = self.solver.solve(opt_pav, (load,), pts)
        st0 = resp.strain_results[0]
        eps_t = max(abs(st0.get("epsilon_r") or 0.0), abs(st0.get("epsilon_t") or 0.0))
        st1 = resp.strain_results[1]
        eps_v = abs(st1.get("epsilon_z") or 0.0)
        e_bc = float(opt_pav.layers[0].elastic_modulus)
        
        from mechanistic_solver.design.adequacy import check_structural_adequacy
        adequacy = check_structural_adequacy(eps_t, e_bc, eps_v, design_traffic_msa)
        
        recs = self.recs_engine.generate_recommendations(opt_pav, adequacy, cost_res)
        
        return {
            "converged": opt_res["converged"],
            "optimal_cost": opt_res["optimal_cost"],
            "optimal_thicknesses": {l.name: l.thickness for l in opt_pav.layers},
            "recommendations": recs,
            "cost_breakdown": cost_res
        }
pre = dict
