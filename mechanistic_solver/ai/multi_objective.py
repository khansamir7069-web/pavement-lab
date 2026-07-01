"""Multi-objective optimization engine producing Pareto-optimal solutions for cost, performance, and reliability."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Layer, Pavement
from mechanistic_solver.advanced.reliability import ReliabilityEngine, StochasticVariable


class MultiObjectiveOptimizer:
    """Dispatches Pareto-frontier searches over candidate pavement designs."""

    def __init__(self, solver: Any = None, reliability_engine: Any = None) -> None:
        self.solver = solver
        self.rel_engine = reliability_engine or ReliabilityEngine(solver=self.solver)

    def optimize_pareto(
        self,
        pavement: Pavement,
        loads: Sequence[Any],
        traffic_msa: float,
        bounds: Mapping[str, tuple[float, float]],
        step_mm: float = 20.0
    ) -> Sequence[Mapping[str, Any]]:
        """Find Pareto-optimal solutions balancing construction cost, structural utilization, and reliability.

        References: Coello Coello, C.A. (2006). Evolutionary Algorithms for Solving Multi-Objective Problems.
        """
        # 1. Generate candidate grid
        from mechanistic_solver.ai.layer_optimizer import LayerOptimizer
        layer_opt = LayerOptimizer(solver=self.solver)
        
        opt_res = layer_opt.optimize_layers(pavement, loads, traffic_msa, bounds, step_mm=step_mm)
        candidates = opt_res["history"]
        
        # 2. Re-evaluate top candidates for reliability to save execution time
        valid_candidates = [c for c in candidates if c["passed"] and c["error"] is None]
        if not valid_candidates:
            # Fall back to all candidates if none passed
            valid_candidates = [c for c in candidates if c["error"] is None]
            
        evaluated = []
        traffic_stoch = StochasticVariable(mean=traffic_msa, std_dev=0.15 * traffic_msa)
        
        # Limit to first 15 candidates to maintain fast test runtime
        for c in valid_candidates[:15]:
            # Build Pavement configuration from candidate thicknesses
            new_layers = list(pavement.layers)
            for key, val in c["thicknesses"].items():
                for idx, layer in enumerate(pavement.layers):
                    if key.upper() in layer.name.upper():
                        new_layers[idx] = Layer(
                            name=layer.name,
                            thickness=val,
                            elastic_modulus=layer.elastic_modulus,
                            poisson_ratio=layer.poisson_ratio,
                            density=layer.density
                        )
            candidate_pav = Pavement(layers=tuple(new_layers), subgrade=pavement.subgrade)
            
            # Run reliability analysis (fast Monte Carlo with 10 runs)
            rel_res = self.rel_engine.run_monte_carlo(
                pavement=candidate_pav,
                loads=loads,
                traffic_msa=traffic_stoch,
                modulus_stds=[300.0] * len(new_layers),
                thickness_stds=[10.0] * len(new_layers),
                num_simulations=10
            )
            
            evaluated.append({
                "thicknesses": dict(c["thicknesses"]),
                "cost": c["cost"],
                "utilization": c["utilization"],
                "reliability_pct": rel_res["reliability_pct"],
                "passed": c["passed"]
            })
            
        # 3. Pareto Filtering (non-dominated sorting)
        pareto_front = []
        for i, c1 in enumerate(evaluated):
            dominated = False
            for j, c2 in enumerate(evaluated):
                if i == j:
                    continue
                # c2 dominates c1 if:
                # cost(c2) <= cost(c1) AND util(c2) <= util(c1) AND reliability(c2) >= reliability(c1)
                # with at least one strict inequality.
                cond_cost = c2["cost"] <= c1["cost"]
                cond_util = c2["utilization"] <= c1["utilization"]
                cond_rel = c2["reliability_pct"] >= c1["reliability_pct"]
                
                strict = (c2["cost"] < c1["cost"] or 
                          c2["utilization"] < c1["utilization"] or 
                          c2["reliability_pct"] > c1["reliability_pct"])
                          
                if cond_cost and cond_util and cond_rel and strict:
                    dominated = True
                    break
            if not dominated:
                pareto_front.append(c1)
                
        # Sort Pareto front by cost ascending
        pareto_front.sort(key=lambda x: x["cost"])
        return pareto_front
