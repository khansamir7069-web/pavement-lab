"""Explainable local AI engineering assistant providing context-aware design answers from project data."""
from __future__ import annotations

import re
from typing import Any, Mapping


class AIEngineerAssistant:
    """Heuristic rule-based AI assistant answering queries using RoadX pavement records."""

    def __init__(self, pavement: Any, adequacy_result: Mapping[str, Any], cost_result: Mapping[str, Any]) -> None:
        self.pavement = pavement
        self.adequacy = adequacy_result
        self.cost = cost_result

    def ask(self, question: str) -> str:
        """Parse engineering query and format explainable answers based on deterministic results.

        References: IRC:37-2018 Guidelines for the Design of Flexible Pavements.
        """
        q = question.lower().strip()
        
        # 1. Governing failure mode queries
        if "failure" in q or "governing" in q:
            mode = self.adequacy["governing_failure_mode"].upper()
            fatigue_u = self.adequacy["utilization_ratios"]["fatigue"]
            rutting_u = self.adequacy["utilization_ratios"]["rutting"]
            
            if mode == "NONE":
                return (
                    "The pavement is structurally adequate. There are no active failure modes. "
                    f"Fatigue utilization is {fatigue_u*100:.1f}%, and Rutting utilization is {rutting_u*100:.1f}%."
                )
            else:
                return (
                    f"The governing failure mode is {mode}. "
                    f"Fatigue utilization is {fatigue_u*100:.1f}%, and Rutting utilization is {rutting_u*100:.1f}%. "
                    f"The design fails structural limits because the maximum utilization ratio exceeds 100%."
                )
                
        # 2. Cost optimization queries
        elif "optimize cost" in q or "reduce cost" in q or "expensive" in q:
            sensitivities = self.cost["cost_sensitivity"]
            # Find the most cost-sensitive layer
            most_sensitive = max(sensitivities, key=lambda x: x["cost_sensitivity_per_mm"])
            name = most_sensitive["layer_name"]
            rate = most_sensitive["cost_sensitivity_per_mm"]
            
            return (
                f"To optimize cost, consider reducing the thickness of the '{name}' layer. "
                f"This layer has the highest cost sensitivity of {rate:.2f} currency units per mm of thickness. "
                "Ensure that any reduction is verified by the solver to maintain structural safety."
            )
            
        # 3. IRC:37 queries
        elif "irc" in q or "standards" in q:
            return (
                "IRC:37-2018 defines design criteria for flexible pavements in India. "
                "It mandates checking the tensile strain (epsilon_t) at the bottom of the bituminous layer "
                "to prevent fatigue cracking, and the vertical compressive strain (epsilon_v) at the top "
                "of the subgrade soil to prevent rutting deformation."
            )
            
        # 4. Layer properties queries
        elif "layer" in q or "thickness" in q:
            lines = ["Pavement Layer Inventory:"]
            for i, layer in enumerate(self.pavement.layers):
                lines.append(f"- Layer {i}: '{layer.name}', Thickness={layer.thickness} mm, Modulus={layer.elastic_modulus} MPa")
            lines.append(f"- Subgrade: '{self.pavement.subgrade.name}', Modulus={self.pavement.subgrade.elastic_modulus} MPa")
            return "\n".join(lines)
            
        # Default fallback
        else:
            return (
                "Assistant: I can answer questions about the governing failure modes, cost optimization sensitivities, "
                "or layer properties using the active RoadX project dataset. Please refine your question."
            )
pre = re.compile
