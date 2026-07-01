"""Layer thickness optimization engine verifying every candidate configuration using the solver."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Layer, Pavement, WheelLoad, ObservationPoint
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.adequacy import check_structural_adequacy
from mechanistic_solver.ai.cost_optimizer import CostOptimizer


class LayerOptimizer:
    """Automatically optimizes layer thicknesses to minimize construction costs while verifying safety with the solver."""

    def __init__(self, solver: Any = None, cost_optimizer: Any = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")
        self.cost_opt = cost_optimizer or CostOptimizer()

    def optimize_layers(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        design_traffic_msa: float,
        bounds: Mapping[str, tuple[float, float]],  # e.g., {"BC": (40.0, 150.0), "WMM": (100.0, 250.0)}
        step_mm: float = 10.0
    ) -> Mapping[str, Any]:
        """Iteratively search for the thinnest layer configurations that satisfy design adequacy.

        Reference: IRC:37-2018 (Minimum Thickness Criteria).
        """
        history = []
        best_pavement = None
        min_cost = float("inf")
        
        # Identify layers to optimize
        opt_indices = []
        for idx, layer in enumerate(pavement.layers):
            for key in bounds:
                if key.upper() in layer.name.upper():
                    opt_indices.append((idx, key, bounds[key]))
                    break
                    
        if not opt_indices:
            # Fallback to standard optimization if bounds don't match
            return {
                "optimal_pavement": pavement,
                "optimal_cost": self.cost_opt.calculate_pavement_cost(pavement.layers)["total_project_cost"],
                "history": [],
                "converged": False,
                "warnings": ["No layers matched the optimization bounds."]
            }
            
        # Recursive grid builder or simple nested loops
        # To keep it robust, let's generate grid candidates
        grid_ranges = []
        for idx, key, (low, high) in opt_indices:
            steps = []
            val = low
            while val <= high + 1e-5:
                steps.append(val)
                val += step_mm
            grid_ranges.append((idx, steps))
            
        # Cartesian product of grid ranges
        import itertools
        idx_lists = [item[1] for item in grid_ranges]
        combinations = list(itertools.product(*idx_lists))
        
        # Sort combinations by thickness sum to evaluate thinner (cheaper) designs first
        combinations.sort(key=sum)
        
        converged = False
        for combo in combinations:
            # Construct candidate layers
            new_layers = list(pavement.layers)
            for i, val in enumerate(combo):
                layer_idx = grid_ranges[i][0]
                source = new_layers[layer_idx]
                new_layers[layer_idx] = Layer(
                    name=source.name,
                    thickness=val,
                    elastic_modulus=source.elastic_modulus,
                    poisson_ratio=source.poisson_ratio,
                    density=source.density
                )
                
            candidate_pavement = Pavement(
                layers=tuple(new_layers),
                subgrade=pavement.subgrade,
                surface=pavement.surface,
                boundary=pavement.boundary
            )
            
            # Verify candidate using deterministic solver
            # Build observation points
            h1 = float(new_layers[0].thickness) if new_layers else 150.0
            subgrade_depth = sum(float(l.thickness) for l in new_layers if l.thickness is not None)
            
            pts = [
                ObservationPoint(x=0.0, y=0.0, z=h1),
                ObservationPoint(x=0.0, y=0.0, z=subgrade_depth)
            ]
            
            passed = False
            error_msg = None
            util = 1.0
            
            try:
                resp = self.solver.solve(candidate_pavement, loads, pts)
                st0 = resp.strain_results[0]
                # Solver is compression-positive: take strain magnitudes for the
                # IRC:37 fatigue (tensile) and rutting (compressive) models.
                eps_t = max(abs(st0.get("epsilon_r") or 0.0), abs(st0.get("epsilon_t") or 0.0))
                st1 = resp.strain_results[1]
                eps_v = abs(st1.get("epsilon_z") or 0.0)
                
                e_bc = float(new_layers[0].elastic_modulus)
                adequacy = check_structural_adequacy(eps_t, e_bc, eps_v, design_traffic_msa)
                passed = adequacy["overall_passed"]
                util = max(adequacy["utilization_ratios"]["fatigue"], adequacy["utilization_ratios"]["rutting"])
            except Exception as e:
                error_msg = str(e)
                
            # Cost calculation
            cost_details = self.cost_opt.calculate_pavement_cost(new_layers)
            cost = cost_details["total_project_cost"]
            
            rec = {
                "thicknesses": {opt_indices[i][1]: val for i, val in enumerate(combo)},
                "cost": cost,
                "passed": passed,
                "utilization": util,
                "error": error_msg
            }
            history.append(rec)
            
            if passed and cost < min_cost:
                min_cost = cost
                best_pavement = candidate_pavement
                converged = True
                
        return {
            "optimal_pavement": best_pavement or pavement,
            "optimal_cost": min_cost if best_pavement else self.cost_opt.calculate_pavement_cost(pavement.layers)["total_project_cost"],
            "history": history,
            "converged": converged,
            "warnings": [] if converged else ["No candidate design satisfied adequacy requirements."]
        }
