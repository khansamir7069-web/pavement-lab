"""Validation runner executing batch benchmark cases and running engineering diagnostics."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from mechanistic_solver.validation.parity_models import ParityCase, ParityResult
from mechanistic_solver.validation.parity_runner import ParityRunner
from mechanistic_solver.validation.benchmark_database import BenchmarkCase


class BenchmarkRunner:
    """Batch-executes benchmark validation cases and performs engineering diagnostics on mismatches."""

    def __init__(self, parity_runner: ParityRunner | None = None) -> None:
        self.parity_runner = parity_runner or ParityRunner()

    def run_case(self, case: BenchmarkCase) -> dict[str, Any]:
        """Run a single benchmark case and perform validation checks + diagnostics."""
        run_record = {
            "case_id": case.case_id,
            "is_official": case.is_official,
            "parse_status": case.parse_status,
            "status": "corrupt_case",
            "parity_result": None,
            "diagnostics": [],
            "error_message": case.error_message
        }

        # Handle file issues
        if case.parse_status == "corrupt_json" or case.parse_status == "failed" or case.parity_case is None:
            run_record["status"] = "corrupt_case"
            return run_record

        if case.is_official and case.parse_status == "missing_out":
            run_record["status"] = "skipped_missing_official_output"
            run_record["diagnostics"].append("Skipped: Official benchmark output file (.out) is missing.")
            return run_record

        # Execute parity runner on the valid case
        parity_res = self.parity_runner.run_case(case.parity_case)
        run_record["parity_result"] = parity_res
        
        # Assign case status
        if case.is_official:
            run_record["status"] = "validated_case_pass" if parity_res.overall_passed else "validated_case_fail"
        else:
            run_record["status"] = "template_case_pass" if parity_res.overall_passed else "template_case_fail"

        # If failed, perform engineering diagnostics
        if not parity_res.overall_passed:
            diag_hints = self.perform_diagnostics(case.parity_case, parity_res)
            run_record["diagnostics"].extend(diag_hints)

        return run_record

    def perform_diagnostics(self, case: ParityCase, result: ParityResult) -> list[str]:
        """Perform heuristic engineering diagnostics to help identify why RoadX and IITPAVE outputs mismatch."""
        hints: list[str] = []
        
        # Check load/pressure/radius consistency
        for load in case.loads:
            # P = q * pi * a^2 -> wheel_load (kN) = pressure (MPa) * pi * radius(mm)^2 / 1000
            # Let's check consistency
            expected_load_kn = load.pressure * math.pi * (load.radius ** 2) / 1000.0
            if abs(load.wheel_load - expected_load_kn) > 1.0:
                hints.append(
                    f"Consistency warning: Wheel load ({load.wheel_load} kN) does not match "
                    f"computed load from pressure and radius ({expected_load_kn:.2f} kN). "
                    f"Check for tyre pressure or radius mismatch."
                )

        # Check for unit mismatches
        keys = ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]
        labels = {
            "epsilon_t_bottom_bituminous": "Tensile Strain",
            "epsilon_v_top_subgrade": "Vertical Strain",
            "vertical_stress": "Vertical Stress",
            "deflection": "Deflection"
        }

        for key in keys:
            act = result.roadx_outputs.get(key)
            exp = result.expected_outputs.get(key)
            
            if act is not None and exp is not None and abs(exp) > 1e-15:
                ratio = act / exp
                
                # Check for unit factor of 10^6 (microstrain vs unitless, or Pa vs MPa)
                if abs(ratio - 1e6) / 1e6 < 0.02 or abs(ratio - 1e-6) / 1e-6 < 0.02:
                    hints.append(
                        f"Potential unit mismatch detected for {labels[key]}. Ratio is close to 1e6. "
                        f"Check if values are in microstrains vs strains, or Pascals vs Megapascals."
                    )
                # Check for unit factor of 1000 (m vs mm)
                elif abs(ratio - 1000.0) / 1000.0 < 0.02 or abs(ratio - 0.001) / 0.001 < 0.02:
                    hints.append(
                        f"Potential unit mismatch detected for {labels[key]}. Ratio is close to 1000. "
                        f"Check if values are in meters vs millimeters."
                    )
                # Check for other scaling factor
                elif abs(ratio - 10.0) / 10.0 < 0.02 or abs(ratio - 0.1) / 0.1 < 0.02:
                    hints.append(
                        f"Potential scaling mismatch detected for {labels[key]}. Ratio is close to 10. "
                        f"Check if strain values were multiplied by 10 or 100."
                    )

        # Check for layer ordering / Poisson / modulus mismatch hints
        if case.layers:
            first_layer = case.layers[0]
            if first_layer.elastic_modulus > 100000.0 or first_layer.elastic_modulus < 10.0:
                hints.append(
                    f"Modulus warning: First layer modulus {first_layer.elastic_modulus} MPa is unusual. "
                    f"Verify modulus units (MPa expected) and layer ordering."
                )
            if abs(first_layer.poisson_ratio) > 0.5 or first_layer.poisson_ratio < 0.0:
                hints.append(
                    f"Poisson warning: Poisson's ratio {first_layer.poisson_ratio} is out of typical limits (0 to 0.5)."
                )

        return hints

    def run_batch(self, cases: Sequence[BenchmarkCase]) -> list[dict[str, Any]]:
        """Run batch execution over all discovered cases."""
        return [self.run_case(c) for c in cases]
