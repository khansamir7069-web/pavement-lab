"""Project Archive Deliverable Packaging.

Phase O packages the Word report, database inputs, raw IITPAVE execution runs,
revisions log, and approval checklist into a professional submission ZIP.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.project_exchange import export_project
from app.core.iitpave.installation_manager import get_last_run_info


DISCLAIMER_TEXT = (
    "========================================================================\n"
    "                           IMPORTANT DISCLAIMER\n"
    "========================================================================\n"
    "Submission package is decision-support documentation. Final field execution\n"
    "requires review and sign-off by a qualified pavement engineer.\n"
    "========================================================================\n"
)


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

    # 2. Calculation Summary Text
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

    # 3. Approval Sheet
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

    # Write ZIP package
    with zipfile.ZipFile(archive_out_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Write files
        zip_file.writestr("README_Disclaimer.txt", DISCLAIMER_TEXT)
        zip_file.writestr("ProjectInputs.json", inputs_json_str)
        zip_file.writestr("CalculationSummary.txt", summary_text)
        zip_file.writestr("ApprovalSheet.txt", approval_text)
        zip_file.writestr("RevisionHistoryLog.json", revisions_json_str)

        # Copy Word Report if it exists
        if report_path.is_file():
            zip_file.write(report_path, report_path.name)

        # Include IITPAVE Run Logs if available
        last_run = get_last_run_info()
        if last_run and last_run.get("run_dir"):
            run_dir = Path(last_run["run_dir"])
            for fname in ("iitp_inp.dat", "iitp_out.dat", "stdout.log", "stderr.log", "run_status.json"):
                fpath = run_dir / fname
                if fpath.is_file():
                    zip_file.write(fpath, f"iitpave_files/{fname}")

    return archive_out_path
