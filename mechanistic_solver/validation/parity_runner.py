"""Validation runner executing RoadX solver against expected IITPAVE benchmarks."""
from __future__ import annotations

import datetime
from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import ObservationPoint, Pavement
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.validation.parity_models import ParityCase, ParityResult, ParitySummary
from mechanistic_solver.validation.parity_metrics import (
    absolute_error,
    relative_error,
    within_tolerance,
    mae,
    rmse,
)


class ParityRunner:
    """Runs multilayer solver configurations and performs comparison parity checks."""

    def __init__(self, solver: MechanisticSolver | None = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")

    def run_case(self, case: ParityCase) -> ParityResult:
        """Run a single parity case through the RoadX solver and calculate error metrics."""
        # Convert Case inputs to Pavement
        pavement = Pavement(layers=case.layers, subgrade=case.subgrade)
        
        # Execute RoadX Solver
        response = self.solver.solve(pavement, case.loads, case.observation_points)
        
        # Extract depths of interest in mm
        bit_depth = float(case.layers[0].thickness) if case.layers else 0.0
        subgrade_depth = sum(float(l.thickness) for l in case.layers)
        
        roadx_outputs: dict[str, float | None] = {
            "epsilon_t_bottom_bituminous": None,
            "epsilon_v_top_subgrade": None,
            "vertical_stress": None,
            "deflection": None,
        }
        
        # Match observation points to extract outputs
        for idx, pt in enumerate(case.observation_points):
            # Check bottom of bituminous (point index matching depth bit_depth)
            if abs(pt.z - bit_depth) <= 1.0 and abs(pt.x) < 1e-3 and abs(pt.y) < 1e-3:
                if idx < len(response.strain_results):
                    strain_rec = response.strain_results[idx]
                    eps_r = strain_rec.get("epsilon_r")
                    eps_t = strain_rec.get("epsilon_t")
                    if eps_r is not None and eps_t is not None:
                        # IITPAVE reports the critical horizontal tensile strain
                        # as a positive magnitude; the solver is compression-
                        # positive, so take the magnitude. (x 1e6 microstrain)
                        roadx_outputs["epsilon_t_bottom_bituminous"] = max(abs(eps_r), abs(eps_t)) * 1e6
            
            # Check top of subgrade (point index matching depth subgrade_depth)
            if abs(pt.z - subgrade_depth) <= 1.0 and abs(pt.x) < 1e-3 and abs(pt.y) < 1e-3:
                if idx < len(response.strain_results):
                    strain_rec = response.strain_results[idx]
                    eps_z = strain_rec.get("epsilon_z")
                    if eps_z is not None:
                        # IITPAVE reports the critical vertical compressive strain
                        # as a positive magnitude (x 1e6 microstrain).
                        roadx_outputs["epsilon_v_top_subgrade"] = abs(eps_z) * 1e6
                        
            # Set default vertical stress and deflection from first matching observation point if needed
            if idx == 0:
                if idx < len(response.stress_results):
                    roadx_outputs["vertical_stress"] = response.stress_results[idx].get("sigma_z")
                if idx < len(response.displacement_results):
                    # Convert displacement from meters to millimeters (x 1000)
                    disp_m = response.displacement_results[idx].get("vertical_deflection")
                    if disp_m is not None:
                        roadx_outputs["deflection"] = disp_m * 1000.0

        # Normalization and translation of expected outputs keys
        expected_outputs: dict[str, float | None] = {}
        for key in ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]:
            expected_outputs[key] = None
            
        mapping = {
            "tensile_strain_microstrain": "epsilon_t_bottom_bituminous",
            "vertical_strain_microstrain": "epsilon_v_top_subgrade",
            "vertical_stress_mpa": "vertical_stress",
            "deflection_mm": "deflection"
        }
        
        for k, v in case.expected_iitpave_outputs.items():
            mapped_k = mapping.get(k, k)
            if mapped_k in expected_outputs:
                expected_outputs[mapped_k] = v

        # Calculate errors and tolerances
        abs_errors: dict[str, float | None] = {}
        rel_errors: dict[str, float | None] = {}
        pass_status: dict[str, bool] = {}
        warnings: list[str] = []
        
        # Load tolerances from case or use default (abs=1.0, rel=0.05)
        default_tols = {
            "epsilon_t_bottom_bituminous": {"abs": 5.0, "rel": 0.05},  # 5 microstrain or 5%
            "epsilon_v_top_subgrade": {"abs": 5.0, "rel": 0.05},
            "vertical_stress": {"abs": 0.01, "rel": 0.05},              # 0.01 MPa or 5%
            "deflection": {"abs": 0.05, "rel": 0.05}                    # 0.05 mm or 5%
        }
        
        case_tols = case.tolerance_limits or {}
        
        for key in expected_outputs.keys():
            act = roadx_outputs[key]
            exp = expected_outputs[key]
            
            abs_err = absolute_error(act, exp)
            rel_err = relative_error(act, exp)
            abs_errors[key] = abs_err
            rel_errors[key] = rel_err
            
            if exp is None:
                # If expected value is not specified, it is considered passed/ignored
                pass_status[key] = True
                continue
                
            if act is None:
                pass_status[key] = False
                warnings.append(f"Response parameter {key} was not computed by RoadX.")
                continue
                
            tol = case_tols.get(key, default_tols.get(key, {"abs": 0.01, "rel": 0.05}))
            passed = within_tolerance(act, exp, tol.get("abs", 0.01), tol.get("rel", 0.05))
            pass_status[key] = passed
            if not passed:
                warnings.append(
                    f"Parameter {key} failed parity (RoadX={act:.4f}, expected={exp:.4f}, "
                    f"diff={abs_err:.4f}, rel={rel_err:.4f})"
                )

        overall_passed = all(pass_status.values())

        return ParityResult(
            case_id=case.case_id,
            roadx_outputs=roadx_outputs,
            expected_outputs=expected_outputs,
            absolute_errors=abs_errors,
            relative_errors=rel_errors,
            pass_status=pass_status,
            overall_passed=overall_passed,
            warnings=warnings
        )

    def run_all(self, cases: Sequence[ParityCase]) -> ParitySummary:
        """Run a collection of parity cases and aggregate errors and validation status."""
        results = [self.run_case(c) for c in cases]
        
        total = len(cases)
        passed = sum(1 for r in results if r.overall_passed)
        failed = total - passed
        
        # Calculate MAE and RMSE across all cases
        keys = ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]
        aggregated_metrics: dict[str, float | None] = {}
        
        for key in keys:
            actuals = [r.roadx_outputs[key] for r in results]
            expecteds = [r.expected_outputs[key] for r in results]
            
            aggregated_metrics[f"{key}_mae"] = mae(actuals, expecteds)
            aggregated_metrics[f"{key}_rmse"] = rmse(actuals, expecteds)
            
        # Overall status rules:
        # Multilayer solver outputs remain "experimental" until official benchmark cases are passed.
        # But we assign specific validated run status depending on total passes.
        status = "experimental"
        if total > 0:
            status = "validated_case_pass" if passed == total else "validated_case_fail"
            
        warnings: list[str] = []
        for r in results:
            for w in r.warnings:
                warnings.append(f"Case {r.case_id}: {w}")
                
        return ParitySummary(
            case_results=results,
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            overall_status=status,
            metrics=aggregated_metrics,
            generation_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            warnings=warnings
        )
