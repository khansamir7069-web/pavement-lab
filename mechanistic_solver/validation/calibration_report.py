"""Calibration report generator writing Markdown, JSON, and CSV validation summaries."""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Sequence


class CalibrationReportGenerator:
    """Formats and writes batch calibration results to reports/benchmark/."""

    def generate_markdown(self, run_records: Sequence[dict[str, Any]], stats: dict[str, Any]) -> str:
        """Create a Markdown representation of the calibration report."""
        summary = stats["summary"]
        global_metrics = stats["global_metrics"]
        
        # Determine overall verification status label
        official_runs = [r for r in run_records if r["is_official"]]
        official_passed = [r for r in official_runs if r["status"] == "validated_case_pass"]
        
        is_official_run = len(official_runs) > 0
        overall_maturity = "EXPERIMENTAL"
        if is_official_run:
            if len(official_passed) == len(official_runs):
                overall_maturity = "OFFICIALLY VALIDATED"
            else:
                overall_maturity = "EXPERIMENTAL (VALIDATION FAILED)"

        lines = [
            "# RoadX Multilayer Solver Calibration & Validation Report",
            f"**Overall Solver Maturity:** `{overall_maturity}`",
            "",
            "## 1. Run Summary",
            "",
            "| Statistic | Value |",
            "| :--- | :--- |",
            f"| **Total Cases Ingested** | {summary['total_cases']} |",
            f"| **Valid Runs Completed** | {summary['run_cases']} |",
            f"| **Passed Cases** | {summary['passed_cases']} |",
            f"| **Failed Cases** | {summary['failed_cases']} |",
            f"| **Pass Percentage** | {summary['pass_percentage']:.2f}% |",
            f"| **Dataset Contains Official Data** | {'Yes' if is_official_run else 'No (Template-Only)'} |",
            "",
            "## 2. Accuracy Metrics",
            "",
            "| Response Parameter | MAE | RMSE | MAPE (%) | Max Error | 95% Percentile |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        
        labels = {
            "epsilon_t_bottom_bituminous": "Tensile Strain (bituminous bottom)",
            "epsilon_v_top_subgrade": "Vertical Strain (subgrade top)",
            "vertical_stress": "Vertical Stress (MPa)",
            "deflection": "Deflection (mm)"
        }
        
        for k in ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]:
            m = global_metrics[k]
            mae_str = f"{m['mae']:.4f}" if m["mae"] is not None else "N/A"
            rmse_str = f"{m['rmse']:.4f}" if m["rmse"] is not None else "N/A"
            mape_str = f"{m['mape']:.2f}%" if m["mape"] is not None else "N/A"
            max_str = f"{m['max_error']:.4f}" if m["max_error"] is not None else "N/A"
            pct95_str = f"{m['pct_95_error']:.4f}" if m["pct_95_error"] is not None else "N/A"
            lines.append(f"| {labels[k]} | {mae_str} | {rmse_str} | {mape_str} | {max_str} | {pct95_str} |")
            
        lines.extend([
            "",
            "## 3. Case Detail Log",
            "",
            "| Case ID | Type | Status | Epsilon_T Err (%) | Epsilon_V Err (%) | Stress Err (%) | Deflection Err (%) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ])
        
        for r in run_records:
            case_id = r["case_id"]
            c_type = "Official" if r["is_official"] else "Template"
            status = r["status"].upper()
            
            p_res = r["parity_result"]
            if p_res:
                err_t = p_res.relative_errors.get("epsilon_t_bottom_bituminous")
                err_v = p_res.relative_errors.get("epsilon_v_top_subgrade")
                err_s = p_res.relative_errors.get("vertical_stress")
                err_d = p_res.relative_errors.get("deflection")
                
                t_str = f"{err_t*100.1:.2f}%" if err_t is not None else "N/A"
                v_str = f"{err_v*100.1:.2f}%" if err_v is not None else "N/A"
                s_str = f"{err_s*100.1:.2f}%" if err_s is not None else "N/A"
                d_str = f"{err_d*100.1:.2f}%" if err_d is not None else "N/A"
            else:
                t_str = v_str = s_str = d_str = "N/A"
                
            lines.append(f"| `{case_id}` | {c_type} | `{status}` | {t_str} | {v_str} | {s_str} | {d_str} |")
            
        # Add worst cases and recommendations section
        failed_runs = [r for r in run_records if r["status"] in ["validated_case_fail", "template_case_fail"]]
        if failed_runs:
            lines.extend([
                "",
                "## 4. Failed Cases & Diagnostic Recommendations",
                ""
            ])
            for fr in failed_runs:
                lines.append(f"### Case `{fr['case_id']}`")
                lines.append(f"- **Status:** `{fr['status'].upper()}`")
                if fr["diagnostics"]:
                    lines.append("- **Engineering Hints / Troubleshooting Tips:**")
                    for d in fr["diagnostics"]:
                        lines.append(f"  - *{d}*")
                else:
                    lines.append("- No diagnostics triggered.")
                lines.append("")

        return "\n".join(lines)

    def write_csv(self, run_records: Sequence[dict[str, Any]], filepath: str) -> None:
        """Write flat CSV representation of validation comparison outputs."""
        keys = ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Case_ID", "Is_Official", "Status", "Response_Type", 
                "RoadX_Value", "IITPAVE_Value", "Absolute_Error", "Relative_Error", "Pass_Status"
            ])
            
            for r in run_records:
                case_id = r["case_id"]
                is_off = r["is_official"]
                status = r["status"]
                p_res = r["parity_result"]
                
                if p_res:
                    for k in keys:
                        writer.writerow([
                            case_id, is_off, status, k,
                            p_res.roadx_outputs.get(k),
                            p_res.expected_outputs.get(k),
                            p_res.absolute_errors.get(k),
                            p_res.relative_errors.get(k),
                            p_res.pass_status.get(k, False)
                        ])
                else:
                    writer.writerow([case_id, is_off, status, "all", "", "", "", "", False])

    def save_reports(
        self,
        run_records: Sequence[dict[str, Any]],
        stats: dict[str, Any],
        output_dir: str
    ) -> tuple[str, str, str]:
        """Save Markdown, JSON, and CSV reports to output directory."""
        os.makedirs(output_dir, exist_ok=True)
        
        md_content = self.generate_markdown(run_records, stats)
        
        # Serialize JSON
        serializable_records = []
        for r in run_records:
            ser_rec = dict(r)
            if r["parity_result"]:
                ser_rec["parity_result"] = r["parity_result"].to_dict()
            serializable_records.append(ser_rec)
            
        json_data = {
            "statistics": stats,
            "cases": serializable_records
        }
        
        md_path = os.path.join(output_dir, "calibration_report.md")
        json_path = os.path.join(output_dir, "calibration_report.json")
        csv_path = os.path.join(output_dir, "calibration_report.csv")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
            
        self.write_csv(run_records, csv_path)
        
        return md_path, json_path, csv_path
