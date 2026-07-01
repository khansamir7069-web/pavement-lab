"""Network-level pavement analysis covering multi-corridor checks and budget prioritizations."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Pavement, WheelLoad, ObservationPoint
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.adequacy import check_structural_adequacy
from mechanistic_solver.enterprise.assets import PavementAsset


class NetworkAnalysisEngine:
    """Performs multi-corridor structural analysis and prioritizes maintenance spending under budget limits."""

    def __init__(self, solver: Any = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")

    def analyze_network(
        self,
        assets: Sequence[PavementAsset],
        load_data: Mapping[str, Any],
        design_traffic_msa: float,
        budget_limit: float
    ) -> Mapping[str, Any]:
        """Perform batch analysis, ranking sections and allocating maintenance budgets based on utilization."""
        load = WheelLoad(wheel_load=load_data["wheel_load"], pressure=load_data["pressure"], radius=load_data["radius"])
        results = []
        
        for asset in assets:
            for sec in asset.sections:
                # 1. Run deterministic solver check
                h1 = float(sec.layers[0].thickness) if sec.layers else 150.0
                subgrade_depth = sum(float(l.thickness) for l in sec.layers if l.thickness is not None)
                
                pts = [
                    ObservationPoint(x=0.0, y=0.0, z=h1),
                    ObservationPoint(x=0.0, y=0.0, z=subgrade_depth)
                ]
                
                passed = False
                max_util = 1.0
                warnings = []
                
                try:
                    resp = self.solver.solve(Pavement(layers=sec.layers, subgrade=sec.subgrade), (load,), pts)
                    st0 = resp.strain_results[0]
                    eps_t = max(abs(st0.get("epsilon_r") or 0.0), abs(st0.get("epsilon_t") or 0.0))
                    st1 = resp.strain_results[1]
                    eps_v = abs(st1.get("epsilon_z") or 0.0)
                    
                    e_bc = float(sec.layers[0].elastic_modulus)
                    adequacy = check_structural_adequacy(eps_t, e_bc, eps_v, design_traffic_msa)
                    passed = adequacy["overall_passed"]
                    max_util = max(adequacy["utilization_ratios"]["fatigue"], adequacy["utilization_ratios"]["rutting"])
                    warnings.extend(adequacy["warnings"])
                except Exception as e:
                    warnings.append(f"Solver failed on section {sec.section_id}: {e}")
                    
                # Latest PCI from history
                pci = 100.0
                if sec.condition_history:
                    # Ranks by latest condition record
                    pci = sec.condition_history[-1].pavement_condition_index_pci if hasattr(sec.condition_history[-1], 'pavement_condition_index_pci') else sec.condition_history[-1].roughness_iri
                    
                results.append({
                    "road_id": asset.road_id,
                    "road_name": asset.name,
                    "section_id": sec.section_id,
                    "section_name": sec.name,
                    "max_utilization": max_util,
                    "pci": pci,
                    "passed": passed,
                    "estimated_rehab_cost": max_util * 500000.0,  # rough budget estimation based on utilization
                    "warnings": warnings
                })
                
        # 2. Prioritize: Rank by utilization descending (highest risk first) and PCI ascending
        # We sort by passed (False first), then max_utilization (descending), then pci (ascending)
        results.sort(key=lambda x: (x["passed"], -x["max_utilization"], x["pci"]))
        
        # 3. Budget allocation
        allocated_total = 0.0
        prioritized_actions = []
        
        for item in results:
            rehab_cost = item["estimated_rehab_cost"]
            if allocated_total + rehab_cost <= budget_limit:
                allocated = True
                allocated_total += rehab_cost
            else:
                allocated = False
                
            prioritized_actions.append({
                "section_id": item["section_id"],
                "road_name": item["road_name"],
                "section_name": item["section_name"],
                "max_utilization": item["max_utilization"],
                "passed": item["passed"],
                "rehab_cost": rehab_cost,
                "budget_allocated": allocated
            })
            
        return {
            "network_size_sections": len(results),
            "budget_limit": budget_limit,
            "allocated_total": allocated_total,
            "remaining_budget": budget_limit - allocated_total,
            "prioritized_actions": prioritized_actions,
            "raw_analysis_results": results
        }
