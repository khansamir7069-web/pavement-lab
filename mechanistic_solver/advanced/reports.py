"""Advanced pavement engineering report generator (Markdown and JSON formats)."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping


class AdvancedReportGenerator:
    """Generates comprehensive advanced analysis reports under reports/advanced/."""

    @staticmethod
    def save_reports(
        results: Mapping[str, Any],
        output_dir: str | None = None
    ) -> tuple[str, str]:
        """Save advanced reports to output_dir."""
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "reports", "advanced"
            )
            
        os.makedirs(output_dir, exist_ok=True)
        
        md_path = os.path.join(output_dir, "advanced_report.md")
        json_path = os.path.join(output_dir, "advanced_report.json")
        
        # 1. Compile Markdown
        md_lines = [
            "# RoadX Advanced Pavement Engineering Report",
            f"**Evaluation Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 1. Executive Summary",
            f"- **Active License Tier:** Enterprise",
            f"- **Validation Status:** EXPERIMENTAL",
            ""
        ]
        
        # Viscoelastic summary
        if "viscoelastic" in results:
            ve = results["viscoelastic"]
            md_lines.extend([
                "## 2. Viscoelastic Material Characterization",
                f"- **Reference Temperature:** {ve.get('t_ref', 20.0)} °C",
                f"- **Relaxation Modulus E(t=0.1s):** {ve.get('e_t_0_1s', 0.0):.2f} MPa",
                f"- **Dynamic Modulus |E*|(f=10Hz):** {ve.get('e_star_10hz', 0.0):.2f} MPa",
                ""
            ])
            
        # Temperature summary
        if "temperature" in results:
            t_data = results["temperature"]
            md_lines.extend([
                "## 3. Environmental Temperature Analysis",
                f"- **Surface Temperature:** {t_data.get('surface_temp_celsius', 40.0)} °C",
                f"- **Attenuated Modulus Correction Factor:** {t_data.get('modulus_correction_factor', 1.0):.3f}",
                f"- **Thermal Expansion Strain:** {t_data.get('thermal_strain', 0.0) * 1e6:.1f} microstrain",
                ""
            ])
            
        # Moving load envelope
        if "moving_load" in results:
            ml = results["moving_load"]
            md_lines.extend([
                "## 4. Moving Load Critical Response Envelope",
                f"- **Max Critical Displacement:** {ml.get('max_displacement_mm', 0.0):.4f} mm",
                f"- **Max Tensile Strain:** {ml.get('max_tensile_strain_microstrain', 0.0):.2f} microstrain",
                f"- **Max Compressive Strain:** {ml.get('max_compressive_strain_microstrain', 0.0):.2f} microstrain",
                ""
            ])
            
        # Composite
        if "composite" in results:
            comp = results["composite"]
            md_lines.extend([
                "## 5. Composite Pavement Evaluation",
                f"- **Recommended Overlay Thickness:** {comp.get('overlay_recommendation_mm', 0.0):.1f} mm",
                f"- **Concrete Slab Bending Stress:** {comp.get('rigid_slab_bending_stress_mpa', 0.0):.3f} MPa",
                ""
            ])
            
        # Reliability Monte Carlo
        if "reliability" in results:
            rel = results["reliability"]
            md_lines.extend([
                "## 6. Monte Carlo Reliability Analysis",
                f"- **Total Simulated Runs:** {rel.get('total_simulations', 100)}",
                f"- **Achieved Reliability:** {rel.get('reliability_pct', 0.0):.2f} %",
                f"- **Reliability Index (Beta):** {rel.get('reliability_index_beta', 0.0):.3f}",
                f"- **Failure Probability:** {rel.get('failure_probability', 0.0) * 100.0:.2f} %",
                ""
            ])
            if "sensitivity_ranking" in rel:
                md_lines.extend([
                    "### Sensitivity Rankings:",
                    "| Parameter | Correlation Coefficient | Impact |",
                    "| :--- | :--- | :--- |"
                ])
                for rank in rel["sensitivity_ranking"]:
                    param = rank["parameter"]
                    corr = rank["correlation_coefficient"]
                    impact = "Positive (Increase strengthens)" if corr > 0 else "Negative (Increase weakens)"
                    md_lines.append(f"| `{param}` | {corr:.3f} | {impact} |")
                md_lines.append("")
                
        md_lines.extend([
            "## 7. Traceability Information",
            "- **Viscoelastic Superposition:** Williams-Landel-Ferry (WLF) Shift Relation (1955).",
            "- **Attenuated Temperature Profile:** LTPP Depth Model (FHWA-RD-97-147).",
            "- **Concrete Base Bending Stress:** Westergaard Edge Loading Stress (1926).",
            "- **Asphalt Overlay thickness:** Asphalt Institute MS-17 deflection method.",
            "- **Reliability probit model:** Probit standard normal CDF mapping."
        ])
        
        # Save files
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        return md_path, json_path
