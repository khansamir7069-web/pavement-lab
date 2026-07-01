"""Recommendation engine generating troubleshooting tips for pavement designs."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Pavement


class RecommendationEngine:
    """Generates explanatory engineering design advice based on pavement performance."""

    def generate_recommendations(
        self,
        pavement: Pavement,
        adequacy_result: Mapping[str, Any],
        solver_status: str = "experimental"
    ) -> Sequence[str]:
        """Examine pavement layers, adequacy status, and solver details to output advice."""
        recs: list[str] = []
        
        fatigue_status = adequacy_result["fatigue_status"]
        rutting_status = adequacy_result["rutting_status"]
        governing_mode = adequacy_result["governing_failure_mode"]
        overall_passed = adequacy_result["overall_passed"]

        # 1. Verification results recommendations
        if not overall_passed:
            if governing_mode == "fatigue":
                recs.append(
                    "Fatigue cracking governs failure. Recommendation: Increase the thickness "
                    "of the bituminous layer (first layer) or utilize a stiffer binder course "
                    "(e.g., VG40 mix or modified asphalt binder) to reduce tensile strains at the "
                    "bottom of the bituminous stack."
                )
            elif governing_mode == "rutting":
                recs.append(
                    "Subgrade rutting governs failure. Recommendation: Improve the subgrade/stabilized "
                    "layer strength (e.g., lime/cement soil stabilization) or increase the thickness of the "
                    "granular base/sub-base layers to reduce vertical compressive strains on the subgrade."
                )

        # 2. Stiffness ratio validation
        layers = pavement.layers
        for idx in range(len(layers) - 1):
            curr_mod = float(layers[idx].elastic_modulus)
            next_mod = float(layers[idx + 1].elastic_modulus)
            
            # Warn if modular stiffness increases with depth
            if next_mod > curr_mod:
                recs.append(
                    f"Unrealistic stiffness ratio: Layer '{layers[idx + 1].name}' modulus ({next_mod} MPa) "
                    f"exceeds layer '{layers[idx].name}' modulus ({curr_mod} MPa) directly above it. "
                    f"For traditional flexible pavements, layer moduli should decrease with depth."
                )

        # Check subgrade comparison
        if layers:
            last_mod = float(layers[-1].elastic_modulus)
            sub_mod = float(pavement.subgrade.elastic_modulus)
            if sub_mod > last_mod:
                recs.append(
                    f"Unrealistic stiffness ratio: Subgrade modulus ({sub_mod} MPa) exceeds bottom layer "
                    f"'{layers[-1].name}' modulus ({last_mod} MPa) directly above it."
                )
            
            # Check for excessive modular ratio between granular base and subgrade (e.g. > 5.0)
            if sub_mod > 0.0:
                mod_ratio = last_mod / sub_mod
                if mod_ratio > 5.0:
                    recs.append(
                        f"High stiffness ratio: Modulus ratio of bottom layer '{layers[-1].name}' to subgrade "
                        f"is unusually high ({mod_ratio:.1f}). Verify that the bottom layer stiffness is "
                        f"adequately supported by the subgrade stiffness."
                    )

        # 3. Solver validation status warning
        if solver_status == "experimental" or "experimental" in solver_status:
            recs.append(
                "Maturity Warning: RoadX multilayer solver responses are experimental and have not yet "
                "been validated against official benchmark datasets. Engineering conclusions are preliminary."
            )

        return recs
