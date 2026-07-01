"""Validation report generator formatting parity check summaries as JSON and Markdown."""
from __future__ import annotations

import json
import os
from typing import Any

from mechanistic_solver.validation.parity_models import ParitySummary


class ParityReportGenerator:
    """Formats and writes validation reports to reports/parity/ directory."""

    def generate_markdown(self, summary: ParitySummary) -> str:
        """Create a stylized Markdown report detailing comparison results."""
        lines = [
            "# RoadX Multilayer Solver Parity Report",
            f"**Generated At:** {summary.generation_timestamp}",
            f"**Validation Status:** `{summary.overall_status.upper()}`",
            "",
            "## 1. Summary Statistics",
            "",
            "| Metric | Count / Value |",
            "| :--- | :--- |",
            f"| **Total Cases Run** | {summary.total_cases} |",
            f"| **Passed Cases** | {summary.passed_cases} |",
            f"| **Failed Cases** | {summary.failed_cases} |",
            "",
            "## 2. Global Error Metrics",
            "",
            "| Parameter | MAE | RMSE |",
            "| :--- | :--- | :--- |",
        ]
        
        keys = ["epsilon_t_bottom_bituminous", "epsilon_v_top_subgrade", "vertical_stress", "deflection"]
        labels = {
            "epsilon_t_bottom_bituminous": "Tensile Strain (bituminous bottom)",
            "epsilon_v_top_subgrade": "Vertical Strain (subgrade top)",
            "vertical_stress": "Vertical Stress (MPa)",
            "deflection": "Deflection (mm)"
        }
        
        for k in keys:
            mae_val = summary.metrics.get(f"{k}_mae")
            rmse_val = summary.metrics.get(f"{k}_rmse")
            mae_str = f"{mae_val:.4f}" if mae_val is not None else "N/A"
            rmse_str = f"{rmse_val:.4f}" if rmse_val is not None else "N/A"
            lines.append(f"| {labels[k]} | {mae_str} | {rmse_str} |")
            
        lines.extend([
            "",
            "## 3. Case-by-Case Breakdown",
            ""
        ])
        
        for res in summary.case_results:
            lines.extend([
                f"### Case: `{res.case_id}`",
                f"**Status:** `{'PASSED' if res.overall_passed else 'FAILED'}`",
                "",
                "| Response Parameter | RoadX Value | Expected IITPAVE | Abs Error | Rel Error | Status |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |"
            ])
            for k in keys:
                act = res.roadx_outputs.get(k)
                exp = res.expected_outputs.get(k)
                abs_err = res.absolute_errors.get(k)
                rel_err = res.relative_errors.get(k)
                passed = res.pass_status.get(k, False)
                
                act_str = f"{act:.4f}" if act is not None else "N/A"
                exp_str = f"{exp:.4f}" if exp is not None else "N/A"
                abs_str = f"{abs_err:.4f}" if abs_err is not None else "N/A"
                rel_str = f"{rel_err:.4f}" if rel_err is not None else "N/A"
                status_str = "**PASS**" if passed else "**FAIL**"
                
                lines.append(f"| {labels[k]} | {act_str} | {exp_str} | {abs_str} | {rel_str} | {status_str} |")
            lines.append("")

        if summary.warnings:
            lines.extend([
                "## 4. Warnings & Validation Issues Log",
                ""
            ])
            for w in summary.warnings:
                lines.append(f"- {w}")
            lines.append("")
            
        return "\n".join(lines)

    def generate_json(self, summary: ParitySummary) -> str:
        """Create a clean JSON string representation of the validation report."""
        return json.dumps(summary.to_dict(), indent=2)

    def save_reports(self, summary: ParitySummary, output_dir: str) -> tuple[str, str]:
        """Compile and save both Markdown and JSON reports to disk."""
        os.makedirs(output_dir, exist_ok=True)
        
        md_content = self.generate_markdown(summary)
        json_content = self.generate_json(summary)
        
        md_path = os.path.join(output_dir, "parity_report.md")
        json_path = os.path.join(output_dir, "parity_report.json")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_content)
            
        return md_path, json_path
