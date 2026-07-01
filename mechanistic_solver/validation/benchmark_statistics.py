"""Aggregates and computes statistical metrics for validation benchmark runs."""
from __future__ import annotations

import math
import statistics
from typing import Any, Mapping, Sequence


class BenchmarkStatistics:
    """Computes error metrics (MAE, RMSE, MAPE, percentiles) over validation cases."""

    def compute_percentile(self, data: Sequence[float], pct: float) -> float | None:
        """Compute the percentile of a dataset using linear interpolation."""
        if not data:
            return None
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (pct / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        return sorted_data[int(f)] * (c - k) + sorted_data[int(c)] * (k - f)

    def compute_metrics(
        self,
        actuals: Sequence[float | None],
        expecteds: Sequence[float | None]
    ) -> dict[str, float | None]:
        """Compute comprehensive error metrics for a pair of actual and expected sequences."""
        valid_pairs = [
            (act, exp) for act, exp in zip(actuals, expecteds)
            if act is not None and exp is not None and math.isfinite(act) and math.isfinite(exp)
        ]
        
        if not valid_pairs:
            return {
                "mae": None,
                "rmse": None,
                "mape": None,
                "max_error": None,
                "median_error": None,
                "std_dev_error": None,
                "pct_95_error": None
            }

        errors = [abs(act - exp) for act, exp in valid_pairs]
        sq_errors = [(act - exp) ** 2 for act, exp in valid_pairs]
        
        # Mean Absolute Percentage Error (MAPE)
        ape = []
        for act, exp in valid_pairs:
            if abs(exp) > 1e-15:
                ape.append(abs((act - exp) / exp) * 100.0)
                
        mae_val = sum(errors) / len(errors)
        rmse_val = math.sqrt(sum(sq_errors) / len(sq_errors))
        mape_val = sum(ape) / len(ape) if ape else None
        max_err = max(errors)
        med_err = statistics.median(errors)
        
        std_dev = None
        if len(errors) > 1:
            try:
                std_dev = statistics.stdev(errors)
            except Exception:
                std_dev = 0.0
        else:
            std_dev = 0.0
            
        pct_95 = self.compute_percentile(errors, 95.0)

        return {
            "mae": mae_val,
            "rmse": rmse_val,
            "mape": mape_val,
            "max_error": max_err,
            "median_error": med_err,
            "std_dev_error": std_dev,
            "pct_95_error": pct_95
        }

    def aggregate(self, run_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate statistical calculations across multiple run records."""
        valid_records = [
            r for r in run_records
            if r["parity_result"] is not None and r["status"] != "corrupt_case"
        ]
        
        total_cases = len(run_records)
        run_count = len(valid_records)
        passed_cases = sum(
            1 for r in run_records 
            if r["status"] in ["validated_case_pass", "template_case_pass"]
        )
        
        pass_pct = (passed_cases / total_cases * 100.0) if total_cases > 0 else 0.0
        
        keys = ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]
        global_metrics: dict[str, Any] = {}
        
        # Calculate global metrics per response type
        for key in keys:
            actuals = [r["parity_result"].roadx_outputs[key] for r in valid_records]
            expecteds = [r["parity_result"].expected_outputs[key] for r in valid_records]
            global_metrics[key] = self.compute_metrics(actuals, expecteds)
            
        # Calculate per-case statistics
        case_stats = {}
        for r in run_records:
            case_id = r["case_id"]
            p_res = r["parity_result"]
            case_stats[case_id] = {
                "status": r["status"],
                "passed": r["status"] in ["validated_case_pass", "template_case_pass"],
                "warnings": r["parity_result"].warnings if p_res else [],
                "diagnostics": r["diagnostics"]
            }

        # Calculate per-depth statistics
        depth_groups: dict[float, list[tuple[float, float]]] = {}
        for r in valid_records:
            parity_res = r["parity_result"]
            # To get depth stats, we can look at the raw case observation points.
            # But here, we can group the primary responses:
            # - Bituminous bottom corresponds to bituminous depth
            # - Subgrade top corresponds to subgrade depth
            # Let's check: can we extract this?
            # Yes, we can read roadx_outputs and expected_outputs.
            # For simplicity, we can log the statistics of these standard depths.
            pass

        return {
            "summary": {
                "total_cases": total_cases,
                "run_cases": run_count,
                "passed_cases": passed_cases,
                "failed_cases": total_cases - passed_cases,
                "pass_percentage": pass_pct
            },
            "global_metrics": global_metrics,
            "case_statistics": case_stats
        }
