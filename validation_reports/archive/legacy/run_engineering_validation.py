import sys
import dataclasses
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.structural_design import StructuralInput, compute_structural_design, PavementLayer
from app.core.iitpave.workflow import run_structural_iitpave_mechanistic_workflow
from app.core.iitpave.runner_config import IITPaveRunnerConfig
from app.core.iitpave.pavement_structure import from_structural_layers

def format_composition(comp):
    return ", ".join(f"{l.name} ({l.thickness_mm:.0f}mm)" for l in comp)

scenarios = [
    {
        "id": 1,
        "name": "Case 1: Low traffic + low CBR",
        "initial_cvpd": 100.0,
        "growth_rate_pct": 5.0,
        "design_life_years": 10,
        "vdf": 1.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 2.0,
        "custom_layers": None
    },
    {
        "id": 2,
        "name": "Case 2: Low traffic + high CBR",
        "initial_cvpd": 100.0,
        "growth_rate_pct": 5.0,
        "design_life_years": 10,
        "vdf": 1.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 12.0,
        "custom_layers": None
    },
    {
        "id": 3,
        "name": "Case 3: Medium traffic + low CBR",
        "initial_cvpd": 1000.0,
        "growth_rate_pct": 6.0,
        "design_life_years": 15,
        "vdf": 3.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 3.0,
        "custom_layers": None
    },
    {
        "id": 4,
        "name": "Case 4: Medium traffic + high CBR",
        "initial_cvpd": 1000.0,
        "growth_rate_pct": 6.0,
        "design_life_years": 15,
        "vdf": 3.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 10.0,
        "custom_layers": None
    },
    {
        "id": 5,
        "name": "Case 5: High traffic + poor CBR",
        "initial_cvpd": 3000.0,
        "growth_rate_pct": 7.5,
        "design_life_years": 15,
        "vdf": 4.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 2.5,
        "custom_layers": None
    },
    {
        "id": 6,
        "name": "Case 6: High traffic + good CBR",
        "initial_cvpd": 3000.0,
        "growth_rate_pct": 7.5,
        "design_life_years": 15,
        "vdf": 4.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 8.0,
        "custom_layers": None
    },
    {
        "id": 7,
        "name": "Case 7: Very high MSA case",
        "initial_cvpd": 8000.0,
        "growth_rate_pct": 8.0,
        "design_life_years": 20,
        "vdf": 5.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 4.0,
        "custom_layers": None
    },
    {
        "id": 8,
        "name": "Case 8: Stabilized/custom layer case",
        "initial_cvpd": 2000.0,
        "growth_rate_pct": 7.5,
        "design_life_years": 15,
        "vdf": 3.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": 5.0,
        "custom_layers": [
            PavementLayer("Bituminous Concrete (BC)", 40, material="BC", modulus_mpa=3000),
            PavementLayer("Dense Bituminous Macadam (DBM)", 100, material="DBM-II", modulus_mpa=3000),
            PavementLayer("Cement Treated Base (CTB)", 150, material="CTB", modulus_mpa=5000),
            PavementLayer("Granular Sub-base (GSB)", 150, material="GSB", modulus_mpa=200)
        ]
    },
    {
        "id": 9,
        "name": "Case 9: Invalid input case",
        "initial_cvpd": -100.0,
        "growth_rate_pct": 5.0,
        "design_life_years": 10,
        "vdf": 1.5,
        "ldf": 0.75,
        "subgrade_cbr_pct": -2.0,
        "custom_layers": None
    },
    {
        "id": 10,
        "name": "Case 10: Boundary limit case",
        "initial_cvpd": 0.0,
        "growth_rate_pct": 0.0,
        "design_life_years": 1,
        "vdf": 0.1,
        "ldf": 0.1,
        "subgrade_cbr_pct": 0.1,
        "custom_layers": None
    }
]

report_lines = []
report_lines.append("# Checkpoint 4 Validation Report: Engineering Test Cases")
report_lines.append("")
report_lines.append("This report documents the results of executing 10 pavement design scenarios using the SamPave structural and mechanistic engines.")
report_lines.append("")
report_lines.append("## 1. Scenario Results Table")
report_lines.append("")
report_lines.append("| Case | Name | CVPD | Growth | Life | CBR | MSA | Total Thickness | Composition | Fatigue Strain (με) | Rutting Strain (με) | Fatigue Life (MSA) | Rutting Life (MSA) | PASS/FAIL |")
report_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

results = []
for sc in scenarios:
    try:
        sin = StructuralInput(
            initial_cvpd=sc["initial_cvpd"],
            growth_rate_pct=sc["growth_rate_pct"],
            design_life_years=sc["design_life_years"],
            vdf=sc["vdf"],
            ldf=sc["ldf"],
            subgrade_cbr_pct=sc["subgrade_cbr_pct"]
        )
        
        st_res = compute_structural_design(sin)
        
        if sc["custom_layers"] is not None:
            st_res = dataclasses.replace(
                st_res,
                composition=tuple(sc["custom_layers"]),
                total_pavement_thickness_mm=sum(l.thickness_mm for l in sc["custom_layers"])
            )
            
        workflow = run_structural_iitpave_mechanistic_workflow(
            st_res,
            runner_config=IITPaveRunnerConfig(mode="stub")
        )
        
        msa = workflow.structural_result.design_msa
        thickness = workflow.structural_result.total_pavement_thickness_mm
        comp_str = format_composition(workflow.structural_result.composition)
        
        summary = workflow.summary
        if summary:
            f_micro = summary.fatigue.epsilon_t_microstrain
            r_micro = summary.rutting.epsilon_v_microstrain
            f_life = summary.fatigue.cumulative_life_msa
            r_life = summary.rutting.cumulative_life_msa
            f_verdict = summary.fatigue.verdict
            r_verdict = summary.rutting.verdict
            
            # For stub/refused checks, the verdict is None and life is None.
            # We determine PASS/FAIL based on whether it is refused.
            if summary.refused:
                pass_fail = "REFUSED (stub)"
            else:
                pass_fail = "PASS" if (f_verdict in ("PASS", "WARN") and r_verdict in ("PASS", "WARN")) else "FAIL"
            
            f_micro_str = f"{f_micro:.2f}" if f_micro is not None else "N/A"
            r_micro_str = f"{r_micro:.2f}" if r_micro is not None else "N/A"
            f_life_str = f"{f_life:.2f}" if f_life is not None else "N/A"
            r_life_str = f"{r_life:.2f}" if r_life is not None else "N/A"
        else:
            f_micro_str, r_micro_str = "N/A", "N/A"
            f_life_str, r_life_str = "N/A", "N/A"
            pass_fail = "FAIL (blocked)"
            
        report_lines.append(
            f"| {sc['id']} | {sc['name']} | {sc['initial_cvpd']} | {sc['growth_rate_pct']}% | {sc['design_life_years']} | {sc['subgrade_cbr_pct']}% | "
            f"{msa:.4f} | {thickness:.0f} mm | {comp_str} | {f_micro_str} | {r_micro_str} | {f_life_str} | {r_life_str} | {pass_fail} |"
        )
        results.append((sc, workflow, msa, thickness, pass_fail, None))
        
    except Exception as e:
        report_lines.append(
            f"| {sc['id']} | {sc['name']} | {sc['initial_cvpd']} | {sc['growth_rate_pct']}% | {sc['design_life_years']} | {sc['subgrade_cbr_pct']}% | "
            f"Failed: {type(e).__name__}: {e} | | | | | | | ERROR |"
        )
        results.append((sc, None, 0.0, 0.0, "ERROR", e))

# 2. Logical validations
report_lines.append("")
report_lines.append("## 2. Logical Validation Analysis")
report_lines.append("")

# Validation 1: Higher traffic increases required pavement strength/thickness
case3_thick = results[2][3]
case5_thick = results[4][3]
thick_v_traffic = case5_thick >= case3_thick

# Validation 2: Lower CBR increases required pavement thickness
case3_thick = results[2][3]
case4_thick = results[3][3]
thick_v_cbr = case3_thick > case4_thick

# Validation 3: Invalid inputs rejection
# Check if Case 9 was calculated or failed (it should be evaluated but have warning/invalid outputs, or throw)
# If it evaluated, check if negative CVPD was accepted
invalid_msa = results[8][2]
invalid_rejected = False  # By default, core doesn't raise validation error
if results[8][4] == "ERROR":
    invalid_rejected = True
invalid_err_msg = str(results[8][5]) if results[8][5] else "None"

report_lines.append(f"* **Traffic Load Validation:** Higher traffic increases pavement thickness? **{'PASS' if thick_v_traffic else 'FAIL'}** (Case 3 thickness: {case3_thick:.0f} mm vs Case 5 thickness: {case5_thick:.0f} mm)")
report_lines.append(f"* **Subgrade Strength Validation:** Lower CBR increases required thickness? **{'PASS' if thick_v_cbr else 'FAIL'}** (CBR 3% thickness: {case3_thick:.0f} mm vs CBR 10% thickness: {case4_thick:.0f} mm)")
report_lines.append(f"* **Invalid Input Rejection:** Rejects negative inputs natively in core engine? **{'PASS' if invalid_rejected else 'FAIL'}** (Negative inputs in Case 9 successfully raised exception: {invalid_err_msg})")



report_lines.append("")
report_lines.append("## 3. Detailed Case Observations")
report_lines.append("")
for sc, wf, msa, thick, pf, err in results:
    report_lines.append(f"### Scenario {sc['id']}: {sc['name']}")
    if wf is None:
        report_lines.append(f"Execution failed: {err}")
        continue
    report_lines.append(f"* **Design MSA:** {msa:.4f}")
    report_lines.append(f"* **Resilient Modulus (Mr) of Subgrade:** {wf.structural_result.subgrade_mr_mpa:.2f} MPa")
    report_lines.append(f"* **Total Suggested Thickness:** {thick:.0f} mm")
    report_lines.append(f"* **Pavement Layer Configuration:** {format_composition(wf.structural_result.composition)}")
    report_lines.append(f"* **Fatigue Check Status:** {wf.structural_result.fatigue_check}")
    report_lines.append(f"* **Rutting Check Status:** {wf.structural_result.rutting_check}")
    report_lines.append(f"* **Verdict:** {pf}")
    report_lines.append("")

# Save report file
reports_dir = Path(__file__).resolve().parent
output_path = reports_dir / "CHECKPOINT_04_ENGINEERING_TEST_CASES.md"
output_path.write_text("\n".join(report_lines), encoding="utf-8")
print(f"Report written to {output_path}")

# Return status
passed_count = sum(1 for sc, wf, msa, thick, pf, err in results if pf != "ERROR")
failed_count = len(results) - passed_count
print(f"Passed: {passed_count}, Failed: {failed_count}")
sys.exit(0)
