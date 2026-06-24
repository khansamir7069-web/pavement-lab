"""Project Archive Deliverable Packaging.

Phase 5 packages the Word report, Excel sheets, database inputs, raw IITPAVE execution runs,
revisions log, and design audit report into a structured, client-ready ZIP package.
"""
from __future__ import annotations

import json
import zipfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.project_exchange import export_project
from app.core.iitpave.installation_manager import get_last_run_info
from app.reports.excel_exporter import build_boq_excel, build_input_data_excel, build_layer_summary_excel

DISCLAIMER_TEXT = (
    "========================================================================\n"
    "                           IMPORTANT DISCLAIMER\n"
    "========================================================================\n"
    "Submission package is decision-support documentation. Final field execution\n"
    "requires review and sign-off by a qualified pavement engineer.\n"
    "========================================================================\n"
)


def compile_audit_report_text(project_id: int, db) -> str:
    """Run design audit and format a text summary report."""
    try:
        from app.engineering.design_audit import run_project_audit
        audit = run_project_audit(project_id, db)
    except Exception as e:
        return f"Failed to run design audit: {e}"

    p = db.get_project(project_id)
    lines = [
        "========================================================================",
        "                       PAVEMENT DESIGN AUDIT REPORT",
        "========================================================================",
        f"Project Name     : {p.work_name if p else 'N/A'}",
        f"Audit Score      : {audit.score}/100",
        f"Risk Level       : {audit.risk_level}",
        f"Readiness Status : {audit.readiness_status}",
        f"Generated On     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "------------------------------------------------------------------------",
        "Audit Findings & Recommendations:",
        ""
    ]
    if not audit.findings:
        lines.append("No findings or warnings recorded. The design meets all checked criteria.")
    else:
        for idx, f in enumerate(audit.findings, start=1):
            lines.append(f"{idx}. [{f.severity.upper()}] Module: {f.module}")
            lines.append(f"   Issue: {f.issue}")
            lines.append(f"   Recommendation: {f.recommendation}")
            lines.append(f"   Engineering Reason: {f.engineering_reason}")
            lines.append("")
    return "\n".join(lines)


def compile_verification_report_text(project_id: int, db) -> str:
    """Format a summary verification report for IITPAVE mechanistic checks."""
    mech = db.latest_mechanistic_validation(project_id)
    if not mech or mech.refused:
        return "IITPAVE verification file not available."

    p = db.get_project(project_id)
    lines = [
        "========================================================================",
        "                 IITPAVE MECHANISTIC VERIFICATION REPORT",
        "========================================================================",
        f"Project Name     : {p.work_name if p else 'N/A'}",
        f"Design Traffic   : {mech.design_msa} MSA",
        f"Fatigue Life     : {mech.fatigue_life_msa} MSA",
        f"Rutting Life     : {mech.rutting_life_msa} MSA",
        f"Fatigue Verdict  : {mech.fatigue_verdict}",
        f"Rutting Verdict  : {mech.rutting_verdict}",
        f"Tensile Strain   : {mech.tensile_strain_micro} microstrain",
        f"Compressive Strain: {mech.compressive_strain_micro} microstrain",
        f"Verification Date: {mech.computed_at.strftime('%Y-%m-%d %H:%M:%S') if mech.computed_at else 'N/A'}",
        "------------------------------------------------------------------------",
        "This report confirms that the pavement structural composition has been checked",
        "against fatigue cracking and rutting failure criteria under mechanistic guidelines."
    ]
    return "\n".join(lines)


def compile_revision_history_text(project_id: int, db) -> str:
    """Compile revision tracking entries into a readable table."""
    p = db.get_project(project_id)
    if not p:
        return "Project not found."
    lines = [
        "========================================================================",
        "                           REVISION HISTORY",
        "========================================================================",
        f"Project Name: {p.work_name}",
        "",
        f"{'Rev':<6} {'Date':<12} {'Engineer':<20} {'Description':<30} {'Reason':<25}",
        "-" * 100
    ]
    # R0
    r0_date = p.created_at.strftime("%Y-%m-%d") if p.created_at else "N/A"
    r0_eng = p.submitted_by or "N/A"
    lines.append(f"{'R0':<6} {r0_date:<12} {r0_eng:<20} {'Initial Design':<30} {'Initial Creation':<25}")

    # Revisions from revisions_json
    revisions_list = []
    if p.revisions_json:
        try:
            revisions_list = json.loads(p.revisions_json)
        except Exception:
            pass

    for r in revisions_list:
        rev_num = r.get("revision_number", 1)
        rev_id = f"R{rev_num}"
        dt_str = r.get("created_date") or r.get("date_time") or ""
        if "T" in dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = dt_str[:10]
        else:
            date_str = dt_str or "N/A"

        eng = r.get("engineer") or r.get("engineer_name") or "N/A"
        desc = r.get("description") or r.get("engineer_note") or "N/A"
        reason = r.get("reason") or "N/A"

        # If engineer_note is a JSON string, extract details
        if isinstance(desc, str) and desc.strip().startswith("{"):
            try:
                note_data = json.loads(desc)
                desc = note_data.get("description") or desc
                eng = note_data.get("engineer") or eng
                reason = note_data.get("reason") or reason
            except Exception:
                pass

        # Trim description/reason to fit layout
        desc_trimmed = desc[:28] + ".." if len(desc) > 30 else desc
        reason_trimmed = reason[:23] + ".." if len(reason) > 25 else reason
        lines.append(f"{rev_id:<6} {date_str:<12} {eng:<20} {desc_trimmed:<30} {reason_trimmed:<25}")

    return "\n".join(lines)


def generate_project_archive(
    db: Any,
    project_id: int,
    report_path: Path | str,
    archive_out_path: Path | str,
) -> Path:
    """Generate a project delivery ZIP archive package containing all reports and metadata."""
    report_path = Path(report_path)
    archive_out_path = Path(archive_out_path)
    archive_out_path.parent.mkdir(parents=True, exist_ok=True)

    project = db.get_project(project_id)
    if not project:
        raise ValueError(f"Project #{project_id} not found.")

    # 1. Serialized Project Inputs JSON
    export_payload = export_project(db, project_id)
    inputs_json_str = json.dumps(export_payload, indent=4, sort_keys=True)

    # 2. Calculation Summary Text (Legacy support)
    summary_lines = [
        DISCLAIMER_TEXT,
        f"Project Name   : {project.work_name}",
        f"Client         : {project.client.name if project.client else 'N/A'}",
        f"Consultant     : {project.consultant or 'N/A'}",
        f"Report ID      : {project.report_id or 'N/A'}",
        f"Review Status  : {project.review_status or 'Draft'}",
        f"Lock State     : {'Locked' if project.locked else 'Unlocked'}",
        f"Lock Date/Time : {project.locked_at or 'N/A'}",
        f"Export Date    : {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}\n",
        "------------------------------------------------------------------------",
        "                         CALCULATION SUMMARY",
        "------------------------------------------------------------------------",
    ]

    # Structural Design
    sd_row = db.latest_structural_design(project_id)
    if sd_row:
        summary_lines.append("\n[Flexible Pavement Design (IRC:37-2018)]")
        summary_lines.append(f"  Design Traffic (MSA)      : {sd_row.design_msa or 'N/A'}")
        summary_lines.append(f"  Subgrade MR (MPa)         : {sd_row.subgrade_mr_mpa or 'N/A'}")
        summary_lines.append(f"  Total Pavement Thick (mm) : {sd_row.total_pavement_thickness_mm or 'N/A'}")
        if sd_row.composition_json:
            try:
                comp = sd_row.composition_json
                if isinstance(comp, str):
                    comp = json.loads(comp)
                layers_list = []
                if isinstance(comp, dict):
                    layers_list = comp.get("layers", [])
                elif isinstance(comp, list):
                    layers_list = comp
                summary_lines.append("  Layer Breakdown:")
                for idx, layer in enumerate(layers_list, start=1):
                    summary_lines.append(
                        f"    - {layer.get('name') or f'Layer {idx}'}: "
                        f"Thickness={layer.get('thickness_mm')} mm, Modulus={layer.get('modulus_mpa')} MPa"
                    )
            except Exception:
                pass

    # Stabilized Design
    stab_row = db.latest_stabilized_design(project_id)
    if stab_row and stab_row.results_json:
        try:
            res = json.loads(stab_row.results_json)
            summary_lines.append("\n[Stabilized Base/Sub-base Design (CTB/CTS)]")
            summary_lines.append(f"  CTB thickness (mm) : {res.get('inputs', {}).get('ctb_thickness_mm', 'N/A')}")
            summary_lines.append(f"  CTB modulus (MPa)   : {res.get('inputs', {}).get('ctb_modulus_mpa', 'N/A')}")
            summary_lines.append(f"  CTS thickness (mm) : {res.get('inputs', {}).get('cts_thickness_mm', 'N/A')}")
            summary_lines.append(f"  CTS modulus (MPa)   : {res.get('inputs', {}).get('cts_modulus_mpa', 'N/A')}")
            summary_lines.append(f"  Pavement Thickness Comparison Mode: {res.get('validation_mode', 'Decision Support Mode')}")
        except Exception:
            pass

    # Mechanistic Validation
    mech_val = db.latest_mechanistic_validation(project_id)
    if mech_val:
        summary_lines.append("\n[IITPAVE Mechanistic Verification]")
        summary_lines.append(f"  Fatigue Verdict   : {mech_val.fatigue_verdict or 'N/A'}")
        summary_lines.append(f"  Rutting Verdict   : {mech_val.rutting_verdict or 'N/A'}")
        summary_lines.append(f"  Fatigue Life (MSA): {mech_val.fatigue_life_msa or 'N/A'}")
        summary_lines.append(f"  Rutting Life (MSA): {mech_val.rutting_life_msa or 'N/A'}")
        summary_lines.append(f"  Design Life (MSA) : {mech_val.design_msa or 'N/A'}")

    summary_text = "\n".join(summary_lines)

    # 3. Approval Sheet (Legacy support)
    checklist_dict = {}
    if project.checklist_json:
        try:
            checklist_dict = json.loads(project.checklist_json)
        except Exception:
            pass

    approval_lines = [
        DISCLAIMER_TEXT,
        "------------------------------------------------------------------------",
        "                         ENGINEER SIGN-OFF SHEET",
        "------------------------------------------------------------------------\n",
        f"Project Name   : {project.work_name}",
        f"Client         : {project.client.name if project.client else 'N/A'}",
        f"Consultant     : {project.consultant or 'N/A'}",
        f"Report ID      : {project.report_id or 'N/A'}\n",
        f"Current Review Status: {project.review_status or 'Draft'}\n",
        "Review Checklist Verification:",
        f"  - Design Review Completed             : {'[YES]' if checklist_dict.get('design_review') else '[NO]'}",
        f"  - Input Verification Completed        : {'[YES]' if checklist_dict.get('input_verification') else '[NO]'}",
        f"  - Traffic Assumptions Verified        : {'[YES]' if checklist_dict.get('traffic_verification') else '[NO]'}",
        f"  - Material Assumptions Verified       : {'[YES]' if checklist_dict.get('material_verification') else '[NO]'}",
        f"  - IITPAVE Verification Status         : {checklist_dict.get('iitpave_verification') or 'Not Verified'}\n",
        "Reviewer Notes:",
        f"  {checklist_dict.get('reviewer_notes') or 'No reviewer notes added.'}\n\n",
        "------------------------------------------------------------------------",
        "Sign-off Placeholders:",
        "\n\n\n  _______________________________________",
        "  Signature of Reviewing Engineer",
        "\n  Date: _________________________________",
        "\n  Seal / Registration No: ________________",
    ]
    approval_text = "\n".join(approval_lines)

    # 4. Revision History Log
    revisions_list = []
    if project.revisions_json:
        try:
            revisions_list = json.loads(project.revisions_json)
        except Exception:
            pass
    revisions_json_str = json.dumps(revisions_list, indent=4, sort_keys=True)

    # Compile custom dynamic text reports for structured ZIP folders
    audit_report_text = compile_audit_report_text(project_id, db)
    iitpave_verification_report = compile_verification_report_text(project_id, db)
    revision_history_text = compile_revision_history_text(project_id, db)

    # Build files in a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Generate BOQ Excel
        boq_excel_path = tmp_path / "BOQ_Estimate.xlsx"
        boq_meta = {
            "work_name": project.work_name,
            "client": project.client.name if project.client else "",
            "agency": project.agency or "",
            "submitted_by": project.submitted_by or "",
            "design_standard": "IRC:37-2018",
        }
        try:
            build_boq_excel(boq_excel_path, project_id, db, boq_meta)
        except Exception as e:
            # Fallback/fail-safe Excel creation
            wb = openpyxl.Workbook() if 'openpyxl' in globals() else None
            if wb:
                ws = wb.active
                ws.cell(row=2, column=2, value=f"BOQ generation failed: {e}")
                wb.save(str(boq_excel_path))

        # Generate Input Data Excel
        input_excel_path = tmp_path / "Input_Data.xlsx"
        try:
            build_input_data_excel(input_excel_path, project_id, db)
        except Exception as e:
            pass

        # Generate Layer Summary Excel
        layer_excel_path = tmp_path / "Layer_Summary.xlsx"
        try:
            build_layer_summary_excel(layer_excel_path, project_id, db)
        except Exception as e:
            pass

        # Fetch IITPAVE execution runs
        iitpave_run_log = "IITPAVE verification file not available."
        last_run = get_last_run_info()
        run_dir_files = []
        if last_run and last_run.get("run_dir"):
            run_dir = Path(last_run["run_dir"])
            stdout_path = run_dir / "stdout.log"
            if stdout_path.is_file():
                try:
                    iitpave_run_log = stdout_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            for fname in ("iitp_inp.dat", "iitp_out.dat", "stdout.log", "stderr.log", "run_status.json"):
                fpath = run_dir / fname
                if fpath.is_file():
                    run_dir_files.append((fpath, fname))

        # Write final structured ZIP package
        with zipfile.ZipFile(archive_out_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # ---- Legacy files for backward compatibility ----
            zip_file.writestr("README_Disclaimer.txt", DISCLAIMER_TEXT)
            zip_file.writestr("ProjectInputs.json", inputs_json_str)
            zip_file.writestr("CalculationSummary.txt", summary_text)
            zip_file.writestr("ApprovalSheet.txt", approval_text)
            zip_file.writestr("RevisionHistoryLog.json", revisions_json_str)
            if report_path.is_file():
                zip_file.write(report_path, report_path.name)
            for fpath, name in run_dir_files:
                zip_file.write(fpath, f"iitpave_files/{name}")

            # ---- New Phase 5 structured package folders ----
            # /Reports
            if report_path.is_file():
                zip_file.write(report_path, "Reports/Professional_DPR.docx")
            if boq_excel_path.is_file():
                zip_file.write(boq_excel_path, "Reports/BOQ_Estimate.xlsx")
            zip_file.writestr("Reports/Audit_Report.txt", audit_report_text)

            # /Design
            if input_excel_path.is_file():
                zip_file.write(input_excel_path, "Design/Input_Data.xlsx")
            if layer_excel_path.is_file():
                zip_file.write(layer_excel_path, "Design/Layer_Summary.xlsx")

            # /IITPAVE
            zip_file.writestr("IITPAVE/Run_Log.txt", iitpave_run_log)
            zip_file.writestr("IITPAVE/Verification_Report.txt", iitpave_verification_report)

            # /Archive
            zip_file.writestr("Archive/Revision_History.txt", revision_history_text)

    return archive_out_path
