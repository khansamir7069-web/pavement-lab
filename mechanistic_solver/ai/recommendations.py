"""AI Recommendations generator producing explainable, solver-verified design suggestions."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


class AIRecommendationEngine:
    """Analyzes pavement structural adequacy and cost data to build explainable recommendations."""

    def generate_recommendations(
        self,
        pavement: Any,
        adequacy_result: Mapping[str, Any],
        cost_result: Mapping[str, Any]
    ) -> Sequence[Mapping[str, Any]]:
        """Generate recommendations based on deterministic solver output and cost indicators.

        References: AASHTO Guide for Design of Pavement Structures.
        """
        recs = []
        
        fatigue_util = adequacy_result["utilization_ratios"]["fatigue"]
        rutting_util = adequacy_result["utilization_ratios"]["rutting"]
        passed = adequacy_result["overall_passed"]
        
        # 1. Check Fatigue Cracking
        if fatigue_util > 1.0:
            recs.append({
                "recommendation": "Increase Bituminous Course (BC) thickness",
                "affected_layer": pavement.layers[0].name,
                "engineering_reason": (
                    f"Bituminous tensile strain is excessive ({fatigue_util * 100:.1f}% utilization). "
                    "Increasing the asphalt thickness decreases the tensile strain at the bottom of the BC course."
                ),
                "expected_impact": "Reduces fatigue cracking damage and extends the structural design life.",
                "confidence_score": 0.95,
                "supporting_solver_evidence": {
                    "fatigue_utilization_ratio": fatigue_util,
                    "target_adequacy_status": "FAILED"
                }
            })
            
        # 2. Check Rutting Deformation
        if rutting_util > 1.0:
            recs.append({
                "recommendation": "Increase granular base/subbase thickness or improve subgrade modulus",
                "affected_layer": pavement.subgrade.name,
                "engineering_reason": (
                    f"Vertical compressive strain on top of subgrade is excessive ({rutting_util * 100:.1f}% utilization). "
                    "Stiffening or thickening the upper courses shields the subgrade from high stress pulses."
                ),
                "expected_impact": "Prevents permanent deformation and deep-seated rutting failures.",
                "confidence_score": 0.90,
                "supporting_solver_evidence": {
                    "rutting_utilization_ratio": rutting_util,
                    "target_adequacy_status": "FAILED"
                }
            })
            
        # 3. Check Subgrade Modulus
        if pavement.subgrade.elastic_modulus < 40.0:
            recs.append({
                "recommendation": "Improve subgrade via lime/cement stabilization or select soil replacement",
                "affected_layer": pavement.subgrade.name,
                "engineering_reason": (
                    f"Subgrade design modulus is extremely weak ({pavement.subgrade.elastic_modulus} MPa). "
                    "Stabilizing the top soil layer increases subgrade reaction values."
                ),
                "expected_impact": "Allows thinner granular course designs, significantly reducing structural cost.",
                "confidence_score": 0.88,
                "supporting_solver_evidence": {
                    "subgrade_modulus_mpa": pavement.subgrade.elastic_modulus
                }
            })
            
        # 4. Check Unnecessary Cost
        if passed and max(fatigue_util, rutting_util) < 0.5:
            recs.append({
                "recommendation": "Reduce bituminous course thickness to optimize project costs",
                "affected_layer": pavement.layers[0].name,
                "engineering_reason": (
                    f"Pavement is over-designed (max utilization is only {max(fatigue_util, rutting_util) * 100:.1f}%). "
                    "Reducing thickness cuts unnecessary material expenditure."
                ),
                "expected_impact": "Lowers structural construction volume and saves project budget.",
                "confidence_score": 0.92,
                "supporting_solver_evidence": {
                    "max_utilization_ratio": max(fatigue_util, rutting_util),
                    "total_project_cost": cost_result["total_project_cost"]
                }
            })
            
        # Default safety recommendation if list is empty
        if not recs:
            recs.append({
                "recommendation": "Maintain current pavement configuration",
                "affected_layer": "All",
                "engineering_reason": "Pavement meets structural criteria with balanced utilization ratios.",
                "expected_impact": "Optimal balance between structural safety and cost economy.",
                "confidence_score": 0.85,
                "supporting_solver_evidence": {
                    "fatigue_utilization": fatigue_util,
                    "rutting_utilization": rutting_util
                }
            })
            
        return recs
