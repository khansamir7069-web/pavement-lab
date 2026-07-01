"""Monte Carlo reliability analysis framework, parameter sampling, and sensitivity ranking."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from scipy.stats import norm

from mechanistic_solver.core.models import Layer, Pavement, WheelLoad, ObservationPoint
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.adequacy import check_structural_adequacy


@dataclass(frozen=True)
class StochasticVariable:
    """Represents a stochastic parameter with mean, standard deviation, and distribution type."""
    mean: float
    std_dev: float
    distribution: str = "normal"  # "normal" or "lognormal"

    def sample(self) -> float:
        """Draw a random sample from the defined probability distribution."""
        if self.std_dev <= 0.0:
            return self.mean
            
        if self.distribution.lower() == "lognormal":
            # Convert normal mean and std to lognormal parameters mu and sigma
            var = self.std_dev**2
            mu = math.log(self.mean**2 / math.sqrt(var + self.mean**2))
            sigma = math.sqrt(math.log(var / self.mean**2 + 1.0))
            val = random.lognormvariate(mu, sigma)
        else:
            val = random.normalvariate(self.mean, self.std_dev)
            
        return max(1e-3, val)  # Prevent negative values


class ReliabilityEngine:
    """Orchestrates Monte Carlo pavement adequacy simulations and sensitivity analysis."""

    def __init__(self, solver: Any = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")

    def run_monte_carlo(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        traffic_msa: StochasticVariable,
        modulus_stds: Sequence[float],    # Standard deviations of layer moduli (MPa)
        thickness_stds: Sequence[float],  # Standard deviations of layer thicknesses (mm)
        num_simulations: int = 100
    ) -> Mapping[str, Any]:
        """Execute probabilistic Monte Carlo sweeps to compute reliability and sensitivity rankings.

        References: AASHTOWare Pavement ME Design Reliability Framework.
        """
        random.seed(42)  # For deterministic execution in tests
        
        failures = 0
        samples_history = []
        utilization_history = []
        
        # Build stochastic inputs mapping
        stochastic_moduli = [StochasticVariable(l.elastic_modulus, std) for l, std in zip(pavement.layers, modulus_stds)]
        stochastic_thicknesses = [StochasticVariable(l.thickness, std) for l, std in zip(pavement.layers, thickness_stds) if l.thickness is not None]
        stochastic_subgrade_mod = StochasticVariable(pavement.subgrade.elastic_modulus, modulus_stds[-1] if len(modulus_stds) > len(pavement.layers) else 5.0)
        
        for _ in range(num_simulations):
            # Sample parameters
            sampled_moduli = [var.sample() for var in stochastic_moduli]
            sampled_thicknesses = [var.sample() for var in stochastic_thicknesses]
            sampled_subgrade_mod = stochastic_subgrade_mod.sample()
            sampled_traffic = traffic_msa.sample()
            
            # Reconstruct pavement
            new_layers = []
            thick_idx = 0
            for i, layer in enumerate(pavement.layers):
                if layer.thickness is not None:
                    t = sampled_thicknesses[thick_idx]
                    thick_idx += 1
                else:
                    t = None
                new_layer = Layer(
                    name=layer.name,
                    thickness=t,
                    elastic_modulus=sampled_moduli[i],
                    poisson_ratio=layer.poisson_ratio,
                    density=layer.density
                )
                new_layers.append(new_layer)
                
            new_subgrade = Layer(
                name=pavement.subgrade.name,
                thickness=None,
                elastic_modulus=sampled_subgrade_mod,
                poisson_ratio=pavement.subgrade.poisson_ratio,
                density=pavement.subgrade.density
            )
            
            sim_pavement = Pavement(layers=tuple(new_layers), subgrade=new_subgrade)
            
            # Run solver at critical depth coordinates (bottom of first layer and top of subgrade)
            h1 = float(new_layers[0].thickness) if new_layers else 150.0
            subgrade_depth = sum(float(l.thickness) for l in new_layers if l.thickness is not None)
            
            pts = [
                ObservationPoint(x=0.0, y=0.0, z=h1),
                ObservationPoint(x=0.0, y=0.0, z=subgrade_depth)
            ]
            
            try:
                resp = self.solver.solve(sim_pavement, loads, pts)
                
                # Fatigue strain (compression-positive solver -> use magnitude)
                st0 = resp.strain_results[0]
                eps_t = max(abs(st0.get("epsilon_r") or 0.0), abs(st0.get("epsilon_t") or 0.0))

                # Rutting strain
                st1 = resp.strain_results[1]
                eps_v = abs(st1.get("epsilon_z") or 0.0)
                
                e_bc = float(new_layers[0].elastic_modulus)
                adequacy = check_structural_adequacy(eps_t, e_bc, eps_v, sampled_traffic)
                
                util = max(adequacy["utilization_ratios"]["fatigue"], adequacy["utilization_ratios"]["rutting"])
                utilization_history.append(util)
                
                if not adequacy["overall_passed"]:
                    failures += 1
                    
                # Save sample record for sensitivity analysis
                rec = {
                    "bc_modulus": sampled_moduli[0],
                    "bc_thickness": sampled_thicknesses[0] if sampled_thicknesses else h1,
                    "subgrade_modulus": sampled_subgrade_mod,
                    "traffic": sampled_traffic
                }
                samples_history.append(rec)
            except Exception as e:
                # If solver failed, count as a failure
                failures += 1
                
        # Calculate statistics
        total = len(utilization_history) or 1
        fail_prob = failures / total
        reliability = 1.0 - fail_prob
        
        # Probit calculation for reliability index beta
        # Clamp probability of failure to avoid norm.ppf bounds crash
        p_f_clamped = min(max(fail_prob, 1e-6), 1.0 - 1e-6)
        beta = float(-norm.ppf(p_f_clamped))
        
        # Sensitivity Analysis (Pearson correlation coefficient r)
        sensitivity = {}
        if samples_history and len(utilization_history) > 1:
            mean_y = sum(utilization_history) / total
            var_y = sum((y - mean_y)**2 for y in utilization_history)
            
            keys = ["bc_modulus", "bc_thickness", "subgrade_modulus", "traffic"]
            for key in keys:
                mean_x = sum(s[key] for s in samples_history) / total
                var_x = sum((s[key] - mean_x)**2 for s in samples_history)
                
                cov = sum((s[key] - mean_x) * (y - mean_y) for s, y in zip(samples_history, utilization_history))
                
                denom = math.sqrt(var_x * var_y)
                r_val = cov / denom if denom > 0.0 else 0.0
                sensitivity[key] = r_val
                
        # Sort sensitivity ranking descending by absolute value of correlation
        sorted_sensitivity = sorted(sensitivity.items(), key=lambda item: abs(item[1]), reverse=True)
        
        # Calculate confidence intervals for mean utilization
        mean_util = sum(utilization_history) / total
        std_util = math.sqrt(sum((y - mean_util)**2 for y in utilization_history) / (total - 1)) if total > 1 else 0.0
        margin_of_error = 1.96 * (std_util / math.sqrt(total))
        
        return {
            "total_simulations": total,
            "failed_simulations": failures,
            "failure_probability": fail_prob,
            "reliability_pct": reliability * 100.0,
            "reliability_index_beta": beta,
            "utilization_mean": mean_util,
            "utilization_confidence_interval": [mean_util - margin_of_error, mean_util + margin_of_error],
            "sensitivity_ranking": [{"parameter": k, "correlation_coefficient": v} for k, v in sorted_sensitivity]
        }
