"""Design report generator writing Markdown and JSON summary reports."""
from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Pavement, WheelLoad


class IRCDesignReportGenerator:
    """Formats and writes mechanistic design results to reports/design/."""

    def generate_markdown(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        traffic_msa: float,
        adequacy: Mapping[str, Any],
        opt_result: Mapping[str, Any],
        recs: Sequence[str],
        solver_status: str
    ) -> str:
        """Create a Markdown representation of the design report."""
        fatigue = adequacy["fatigue_status"]
        rutting = adequacy["rutting_status"]
        
        lines = [
            "# RoadX Mechanistic Pavement Design Report",
            f"**Overall Adequacy Verdict:** `{'PASSED' if adequacy['overall_passed'] else 'FAILED'}`",
            f"**Governing Failure Mode:** `{adequacy['governing_failure_mode'].upper()}`",
            f"**Solver Verification Status:** `{solver_status.upper()}`",
            "",
            "## 1. Input Specifications",
            f"- **Design Traffic:** {traffic_msa:.2f} MSA",
            "",
            "### Pavement Layer Stack",
            "",
            "| Layer Name | Thickness (mm) | Modulus (MPa) | Poisson's Ratio | Density (kg/m³) |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        
        for idx, l in enumerate(pavement.layers):
            lines.append(f"| {l.name} | {l.thickness:.1f} | {l.elastic_modulus:.1f} | {l.poisson_ratio:.2f} | {l.density:.1f} |")
            
        sub = pavement.subgrade
        lines.append(f"| Subgrade: {sub.name} | Infinite | {sub.elastic_modulus:.1f} | {sub.poisson_ratio:.2f} | {sub.density:.1f} |")
        
        lines.extend([
            "",
            "### Wheel Load Configuration",
            "",
            "| Load (kN) | Tyre Pressure (MPa) | Contact Radius (mm) |",
            "| :--- | :--- | :--- |"
        ])
        
        for ld in loads:
            lines.append(f"| {ld.wheel_load:.2f} | {ld.pressure:.3f} | {ld.radius:.1f} |")
            
        lines.extend([
            "",
            "## 2. Mechanistic Adequacy Results",
            "",
            "| Check Type | Calculated Strain (µε) | Allowable Life (MSA) | Design Target (MSA) | Utilization | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |"
        ])
        
        # Strains are stored in critical_strains key of adequacy.
        # Let's read them.
        critical_strains = adequacy.get("critical_strains", {})
        eps_t = critical_strains.get("epsilon_t_microstrain", 0.0)
        eps_v = critical_strains.get("epsilon_v_microstrain", 0.0)
        
        t_life = fatigue["allowable_repetitions_msa"]
        v_life = rutting["allowable_repetitions_msa"]
        
        t_life_str = f"{t_life:.2f}" if math_finite(t_life) else "Infinite"
        v_life_str = f"{v_life:.2f}" if math_finite(v_life) else "Infinite"
        
        lines.append(
            f"| **Fatigue (Tensile Strain)** | {eps_t:.2f} | {t_life_str} | {traffic_msa:.2f} | "
            f"{fatigue['utilization_ratio']*100.0:.1f}% | `{'PASS' if fatigue['passed'] else 'FAIL'}` |"
        )
        lines.append(
            f"| **Rutting (Vertical Strain)** | {eps_v:.2f} | {v_life_str} | {traffic_msa:.2f} | "
            f"{rutting['utilization_ratio']*100.0:.1f}% | `{'PASS' if rutting['passed'] else 'FAIL'}` |"
        )
        
        # Optimization History Section
        lines.extend([
            "",
            "## 3. Layer Optimization History",
            f"- **Optimized Bituminous Thickness:** {opt_result['optimal_thickness_mm']:.1f} mm",
            f"- **Optimization Convergence:** `{opt_result['converged']}`",
            "",
            "| Trial | Thickness (mm) | Epsilon_T (µε) | Epsilon_V (µε) | Util Ratio | Pass |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |"
        ])
        
        for t in opt_result["history"]:
            t_idx = t["trial_index"]
            thickness = t["thickness_mm"]
            # Convert unitless to microstrain
            trial_t = t.get("epsilon_t", 0.0) * 1e6
            trial_v = t.get("epsilon_v", 0.0) * 1e6
            lines.append(
                f"| {t_idx} | {thickness:.1f} | {trial_t:.2f} | {trial_v:.2f} | "
                f"{t.get('utilization_ratio', 0.0)*100.0:.1f}% | `{'PASS' if t.get('overall_passed') else 'FAIL'}` |"
            )

        if recs:
            lines.extend([
                "",
                "## 4. Engineering Recommendations",
                ""
            ])
            for r in recs:
                lines.append(f"- {r}")
                
        lines.extend([
            "",
            "## 5. Traceability & Engineering Notes",
            f"- {adequacy['traceability_notes']}",
            f"- Solver maturity status: `{solver_status}`",
            ""
        ])

        return "\n".join(lines)

    def save_reports(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        traffic_msa: float,
        adequacy: Mapping[str, Any],
        opt_result: Mapping[str, Any],
        recs: Sequence[str],
        solver_status: str,
        output_dir: str
    ) -> tuple[str, str]:
        """Save Markdown and JSON reports to disk under output_dir."""
        from mechanistic_solver.core.profiler import global_profiler
        with global_profiler.measure("reporting"):
            os.makedirs(output_dir, exist_ok=True)
        
        md_report = self.generate_markdown(pavement, loads, traffic_msa, adequacy, opt_result, recs, solver_status)
        
        # Serialize JSON
        json_data = {
            "pavement": {
                "layers": [l.to_dict() for l in pavement.layers],
                "subgrade": pavement.subgrade.to_dict()
            },
            "loads": [
                {"wheel_load": ld.wheel_load, "pressure": ld.pressure, "radius": ld.radius} for ld in loads
            ],
            "traffic_msa": traffic_msa,
            "adequacy": dict(adequacy),
            "optimization": {
                "optimal_thickness_mm": opt_result["optimal_thickness_mm"],
                "converged": opt_result["converged"],
                "warnings": opt_result["warnings"],
                "history": list(opt_result["history"])
            },
            "recommendations": list(recs),
            "solver_status": solver_status
        }
        
        md_path = os.path.join(output_dir, "design_report.md")
        json_path = os.path.join(output_dir, "design_report.json")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_report)
            
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
            
        return md_path, json_path


def math_finite(val: float) -> bool:
    import math
    return math.isfinite(val)
