"""Submission panel — Stage 10.

Handles project locking, revision creation, readiness checklist, branding, and final delivery package generation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QGridLayout,
    QDialog,
    QFormLayout,
    QTextEdit,
    QDialogButtonBox,
)

from app.config import REPORTS_DIR
from app.reports.report_builder import build_combined_report, CombinedReportContext
from app.core.project_archive import generate_project_archive
from .common import PageHeader, Card, styled_button


class RevisionCreationDialog(QDialog):
    """Dialog prompting the user for details when creating a project revision."""

    def __init__(self, default_engineer: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Create Project Revision")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.txt_engineer = QLineEdit(default_engineer)
        form.addRow("Engineer Name:", self.txt_engineer)

        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("e.g. Updated subgrade CBR based on fresh soil test")
        form.addRow("Description of Change:", self.txt_desc)

        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("e.g. Site conditions changed; client requested revision")
        self.txt_reason.setMaximumHeight(85)
        form.addRow("Reason for Revision:", self.txt_reason)

        lay.addLayout(form)

        # Dialog Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

    def get_data(self) -> dict:
        return {
            "engineer": self.txt_engineer.text().strip(),
            "description": self.txt_desc.text().strip(),
            "reason": self.txt_reason.toPlainText().strip()
        }


class SubmissionPanel(QWidget):
    """Stage 10 Submission Panel."""

    saved = Signal(int)             # Emits project_id
    project_changed = Signal(int)   # Emits project_id when revision created
    refresh_all_requested = Signal() # Emits when refresh all is clicked

    def __init__(self, db: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._build()
        self._load_branding_ui()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "Submission & Delivery", "Project locking, revisions, and final delivery package"
        )
        self.btn_refresh_all = styled_button("Refresh All Modules", "secondary")
        self.btn_refresh_all.clicked.connect(self.refresh_all_requested.emit)
        self.header.add_action(self.btn_refresh_all)
        lay.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(14)

        # 1. Project Info Banner
        self.proj_banner = QLabel("⚠ No project loaded.")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:10px 14px; "
            "border:1px solid #c9d6ec; border-radius:4px; font-weight:bold;"
        )
        bl.addWidget(self.proj_banner)

        # 2. Lock & Workflow Status Card
        lock_card = Card()
        lock_layout = QHBoxLayout(lock_card)
        lock_layout.setContentsMargins(16, 12, 16, 12)
        lock_layout.setSpacing(16)

        v_lock = QVBoxLayout()
        self.lbl_lock_state = QLabel("<b>Lock Status: Unlocked</b>")
        self.lbl_lock_state.setStyleSheet("font-size:12pt; color:#1d7a3a;")
        self.lbl_lock_details = QLabel("Project can be edited.")
        self.lbl_lock_details.setStyleSheet("color:#6a7180; font-size:9pt;")
        v_lock.addWidget(self.lbl_lock_state)
        v_lock.addWidget(self.lbl_lock_details)
        lock_layout.addLayout(v_lock)

        self.btn_lock_toggle = QPushButton("Lock Design")
        self.btn_lock_toggle.setProperty("class", "Secondary")
        self.btn_lock_toggle.setFixedWidth(140)
        self.btn_lock_toggle.clicked.connect(self._on_lock_toggle)
        lock_layout.addWidget(self.btn_lock_toggle)

        self.btn_create_revision = QPushButton("Create Revision")
        self.btn_create_revision.setProperty("class", "Secondary")
        self.btn_create_revision.setFixedWidth(140)
        self.btn_create_revision.setEnabled(False)
        self.btn_create_revision.clicked.connect(self._on_create_revision)
        lock_layout.addWidget(self.btn_create_revision)

        bl.addWidget(lock_card)

        # 3. Consultant Profile & Branding Card
        brand_card = Card()
        brand_layout = QVBoxLayout(brand_card)
        brand_layout.setContentsMargins(16, 12, 16, 12)
        brand_layout.setSpacing(8)

        brand_layout.addWidget(QLabel("<b>Consultant Profile & Branding Settings</b>"))

        grid = QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(QLabel("Company Name:"), 0, 0)
        self.txt_company = QLineEdit()
        grid.addWidget(self.txt_company, 0, 1)

        grid.addWidget(QLabel("Engineer Name:"), 1, 0)
        self.txt_engineer = QLineEdit()
        grid.addWidget(self.txt_engineer, 1, 1)

        grid.addWidget(QLabel("Registration No (Optional):"), 2, 0)
        self.txt_reg_no = QLineEdit()
        grid.addWidget(self.txt_reg_no, 2, 1)

        grid.addWidget(QLabel("Address:"), 3, 0)
        self.txt_address = QLineEdit()
        grid.addWidget(self.txt_address, 3, 1)

        grid.addWidget(QLabel("Contact Info:"), 4, 0)
        self.txt_contact = QLineEdit()
        grid.addWidget(self.txt_contact, 4, 1)

        grid.addWidget(QLabel("Logo Image:"), 5, 0)
        logo_lay = QHBoxLayout()
        self.txt_logo_path = QLineEdit()
        self.txt_logo_path.setReadOnly(True)
        self.txt_logo_path.setPlaceholderText("Select image for cover page...")
        logo_lay.addWidget(self.txt_logo_path)
        btn_logo = QPushButton("Browse...")
        btn_logo.clicked.connect(self._on_browse_logo)
        logo_lay.addWidget(btn_logo)
        grid.addLayout(logo_lay, 5, 1)

        brand_layout.addLayout(grid)

        self.btn_save_brand = QPushButton("Save Profile")
        self.btn_save_brand.clicked.connect(self._on_save_branding)
        brand_layout.addWidget(self.btn_save_brand)

        bl.addWidget(brand_card)

        # 4. Project Readiness Card
        self.readiness_card = Card()
        rl = QVBoxLayout(self.readiness_card)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(8)
        rl.addWidget(QLabel("<b>Project Readiness Checklist</b>"))
        self.lbl_readiness = QLabel("Loading readiness checks...")
        self.lbl_readiness.setWordWrap(True)
        rl.addWidget(self.lbl_readiness)
        bl.addWidget(self.readiness_card)

        # 5. Export Delivery Package Card
        export_card = Card()
        el = QHBoxLayout(export_card)
        el.setContentsMargins(16, 12, 16, 12)
        v_el = QVBoxLayout()
        v_el.addWidget(QLabel("<b>Submission Deliverables Exporter</b>"))
        v_el.addWidget(QLabel(
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Generate professional Word design reports or compile the complete structured "
            "highway consultancy submission package (.zip)."
            "</span>"
        ))
        el.addLayout(v_el)

        v_buttons = QVBoxLayout()
        self.btn_export_dpr = QPushButton("Generate DPR (.docx)")
        self.btn_export_dpr.setProperty("class", "Secondary")
        self.btn_export_dpr.clicked.connect(self._on_export_dpr)
        v_buttons.addWidget(self.btn_export_dpr)

        self.btn_export_zip = styled_button("Generate Package (.zip)")
        self.btn_export_zip.clicked.connect(self._on_export_zip)
        v_buttons.addWidget(self.btn_export_zip)

        el.addLayout(v_buttons)

        bl.addWidget(export_card)
        bl.addStretch(1)

        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    def _load_branding_ui(self) -> None:
        try:
            from app.core.branding import get_branding_profile
            brand = get_branding_profile()
            self.txt_company.setText(brand.get("company_name", ""))
            self.txt_logo_path.setText(brand.get("logo_path", ""))
            self.txt_address.setText(brand.get("address", ""))
            self.txt_contact.setText(brand.get("contact", ""))
            self.txt_engineer.setText(brand.get("engineer_name", ""))
            self.txt_reg_no.setText(brand.get("registration_number", ""))
        except Exception:
            pass

    def _on_browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.txt_logo_path.setText(path)

    def _on_save_branding(self) -> None:
        profile = {
            "company_name": self.txt_company.text().strip(),
            "logo_path": self.txt_logo_path.text().strip(),
            "address": self.txt_address.text().strip(),
            "contact": self.txt_contact.text().strip(),
            "engineer_name": self.txt_engineer.text().strip(),
            "registration_number": self.txt_reg_no.text().strip()
        }
        try:
            from app.core.branding import save_branding_profile
            save_branding_profile(profile)
            QMessageBox.information(self, "Success", "Consultant branding profile saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save branding profile: {e}")

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self.btn_export_zip.setEnabled(pid is not None)
        self.btn_export_dpr.setEnabled(pid is not None)

        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.lbl_lock_state.setText("<b>Lock Status: N/A</b>")
            self.lbl_lock_state.setStyleSheet("color:#6a7180;")
            self.lbl_lock_details.setText("")
            self.btn_lock_toggle.setEnabled(False)
            self.btn_create_revision.setEnabled(False)
            return

        self.btn_lock_toggle.setEnabled(True)
        self._refresh()

    def _refresh(self) -> None:
        if self._project_id is None:
            return

        p = self.db.get_project(self._project_id)
        if not p:
            return

        # Title banner
        rev_num = p.revision_number or 0
        rev_text = f" (Revision #{rev_num})" if rev_num > 0 else ""
        self.proj_banner.setText(
            f"<b>Project #{p.id}:</b> {p.work_name or '(unnamed)'}{rev_text}"
        )

        # Lock UI
        if p.locked:
            self.lbl_lock_state.setText("<b>Lock Status: FINAL DESIGN LOCKED</b>")
            self.lbl_lock_state.setStyleSheet("font-size:12pt; color:#c0392b; font-weight:bold;")
            self.lbl_lock_details.setText(f"Locked at {p.locked_at or 'unknown time'}. Edits are blocked.")
            self.btn_lock_toggle.setText("Unlock Design")
            self.btn_create_revision.setEnabled(True)
        else:
            self.lbl_lock_state.setText("<b>Lock Status: Unlocked</b>")
            self.lbl_lock_state.setStyleSheet("font-size:12pt; color:#1d7a3a;")
            self.lbl_lock_details.setText("Project calculations and parameters can be modified.")
            self.btn_lock_toggle.setText("Lock Design")
            self.btn_create_revision.setEnabled(False)

        # Compute readiness
        self._check_readiness(p)

    def _check_readiness(self, project: Any) -> None:
        status = self.db.get_module_status(project.id) or {}
        sync_statuses = self.db.get_all_sync_statuses(project.id)
        
        # Modules list to check
        check_modules = [
            ("project", "Project Setup"),
            ("traffic", "Traffic"),
            ("subgrade", "Subgrade"),
            ("structural", "Structural"),
            ("mix_design", "Mix"),
            ("material_qty", "BOQ"),
            ("engineering_review", "Engineering Review"),
            ("submission", "Submission")
        ]
        
        def get_sync_badge(m_key: str, val: str) -> str:
            if val == "empty":
                return "<span style='color:#718096;'>⚫ Not Started</span>"
            elif val == "in_progress":
                return "<span style='color:#3182ce;'>🔵 Pending</span>"
            
            sync_s = sync_statuses.get(m_key, "Synced")
            if sync_s == "Synced":
                return "<span style='color:#1d7a3a;'>🟢 Synced</span>"
            elif sync_s == "Manual Override":
                return "<span style='color:#b7791f;'>🟡 Manual Override</span>"
            else: # Out of Sync
                return "<span style='color:#e53e3e;'>🔴 Out of Sync</span>"

        completed_count = 0
        status_rows = []
        for key, name in check_modules:
            val = status.get(key, "empty")
            if val == "complete":
                completed_count += 1
                status_lbl = "<span style='color:#1d7a3a; font-weight:bold;'>✓ Completed</span>"
            elif val == "needs_review":
                status_lbl = "<span style='color:#d9381e; font-weight:bold;'>⚠ Needs Review</span>"
            elif val == "in_progress":
                status_lbl = "<span style='color:#a06d00; font-weight:bold;'>● In progress</span>"
            elif val == "locked":
                status_lbl = "<span style='color:#4a5568; font-weight:bold;'>🔒 Locked</span>"
                completed_count += 1
            else:
                status_lbl = "<span style='color:#6a7180;'>Not started</span>"
                
            sync_lbl = get_sync_badge(key, val)
            status_rows.append(f"<tr><td>{name}</td><td>{status_lbl}</td><td>{sync_lbl}</td></tr>")
            
        progress_pct = int((completed_count / len(check_modules)) * 100)
        
        # Fetch actual data
        import json
        
        # 1. Project Metadata
        p_name = project.work_name or "Not defined"
        p_client = project.client.name if project.client else "Not defined"
        p_standard = project.design_standard or "Not defined"
        
        # 2. Traffic Analysis
        ta = self.db.latest_traffic_analysis(project.id)
        ta_summary = "No saved data"
        if ta:
            try:
                ta_in = json.loads(ta.inputs_json) if isinstance(ta.inputs_json, str) else ta.inputs_json
                cvpd_val = ta_in.get('initial_cvpd')
                cvpd_str = f"{cvpd_val:.0f}" if cvpd_val is not None else "0"
                growth_val = ta_in.get('growth_rate_pct')
                growth_str = f"{growth_val:.1f}%" if growth_val is not None else "0.0%"
                msa_val = ta.design_msa
                msa_str = f"{msa_val:.2f} MSA" if msa_val is not None else "0.00 MSA"
                ta_summary = f"CVPD: {cvpd_str} · growth: {growth_str} · design: {msa_str}"
            except Exception:
                msa_val = ta.design_msa
                msa_str = f"{msa_val:.2f} MSA" if msa_val is not None else "0.00 MSA"
                ta_summary = f"design: {msa_str}"
                
        # 3. Subgrade
        subgrade_summary = "No saved data"
        if project.subgrade_cbr is not None:
            cbr_str = f"{project.subgrade_cbr:.1f}%"
            mr_val = project.subgrade_mr
            mr_str = f"{mr_val:.1f} MPa" if mr_val is not None else "0.0 MPa"
            subgrade_summary = f"CBR: {cbr_str} · Mr: {mr_str}"
            
        # 4. Structural Design
        sd = self.db.latest_structural_design(project.id)
        sd_summary = "No saved data"
        if sd:
            try:
                sd_comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
                layers_desc_list = []
                for ly in sd_comp:
                    ly_thick = ly.get('thickness_mm')
                    thick_str = f"{float(ly_thick):.0f}mm" if ly_thick is not None else "0mm"
                    layers_desc_list.append(f"{ly.get('name') or ly.get('material') or 'Layer'}: {thick_str}")
                layers_desc = ", ".join(layers_desc_list)
                
                thick_val = sd.total_pavement_thickness_mm
                thick_str = f"{thick_val:.0f}mm" if thick_val is not None else "0mm"
                if layers_desc:
                    sd_summary = f"thickness: {thick_str} ({layers_desc})"
                else:
                    sd_summary = f"thickness: {thick_str}"
            except Exception:
                thick_val = sd.total_pavement_thickness_mm
                thick_str = f"{thick_val:.0f}mm" if thick_val is not None else "0mm"
                sd_summary = f"thickness: {thick_str}"
                
        # 5. Mix Design
        mix = self.db.latest_mix_design(project.id)
        mix_summary = "No saved data"
        if mix:
            mix_type = project.mix_type or "Not selected"
            obc_val = mix.obc_pct
            obc_str = f"{obc_val:.2f}%" if obc_val is not None else "0.00%"
            av_val = mix.air_voids_at_obc_pct
            av_str = f"{av_val:.2f}%" if av_val is not None else "0.00%"
            mix_summary = f"type: {mix_type} · OBC: {obc_str} · Air Voids: {av_str}"
            
        # 6. BOQ
        mq = self.db.latest_material_quantity(project.id)
        mq_summary = "No saved data"
        if mq:
            t_val = mq.total_layer_tonnage_t
            t_str = f"{t_val:.2f} t" if t_val is not None else "0.00 t"
            b_val = mq.total_binder_tonnage_t
            b_str = f"{b_val:.2f} t" if b_val is not None else "0.00 t"
            mq_summary = f"layers: {t_str} · binder: {b_str}"
            
        # 7. Engineering Review
        rev_status = project.review_status or "Draft"
        
        # Parse override history
        override_html = ""
        try:
            history = json.loads(project.override_history_json) if project.override_history_json else []
        except Exception:
            history = []
            
        if history:
            override_rows = []
            for h in history:
                f_name = h.get("field_name", "")
                orig_val = h.get("original_val", "")
                prev_val = h.get("previous_val", "")
                new_val = h.get("new_val", "")
                reason = h.get("reason", "")
                ts = h.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    ts_formatted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    ts_formatted = ts
                user = h.get("user", "Engineer")
                machine = h.get("machine_id", "Local")
                
                if len(reason) > 50:
                    reason = reason[:47] + "..."
                    
                override_rows.append(
                    f"<tr style='border-bottom: 1px solid #eee;'>"
                    f"<td>{h.get('module', 'Structural')}</td>"
                    f"<td>{f_name}</td>"
                    f"<td>{orig_val}</td>"
                    f"<td>{prev_val}</td>"
                    f"<td>{new_val}</td>"
                    f"<td>{reason}</td>"
                    f"<td>{ts_formatted}</td>"
                    f"<td>{user} ({machine})</td>"
                    f"</tr>"
                )
                
            override_html = f"""
            <h3>Manual Override Audit History</h3>
            <table width="100%" cellpadding="6" style="font-size:9pt; border-collapse: collapse; border: 1px solid #ddd; margin-bottom: 16px;">
                <tr style="background-color: #f8f9fa; border-bottom: 1px solid #ddd;">
                    <th align="left">Module</th>
                    <th align="left">Field</th>
                    <th align="left">Original</th>
                    <th align="left">Previous</th>
                    <th align="left">New</th>
                    <th align="left">Reason</th>
                    <th align="left">Timestamp</th>
                    <th align="left">User (Machine)</th>
                </tr>
                {"".join(override_rows)}
            </table>
            """

        # Build readiness UI HTML
        html = f"""
        <h3>Workflow Completion Status Breakdown</h3>
        <table width="100%" cellpadding="6" style="font-size:10pt; border-collapse: collapse; border: 1px solid #ddd; margin-bottom: 16px;">
            <tr style="background-color: #f2f2f2; border-bottom: 1px solid #ddd;">
                <th align="left" width="40%">Module</th>
                <th align="left" width="30%">Completion</th>
                <th align="left" width="30%">Sync Status</th>
            </tr>
            {"".join(status_rows)}
        </table>
        
        <div style="margin-bottom: 16px;">
            <b>Overall Project Progress:</b>
            <div style="background-color: #e0e0e0; border-radius: 4px; width: 100%; height: 18px; margin-top: 4px;">
                <div style="background-color: #1d7a3a; border-radius: 4px; width: {progress_pct}%; height: 18px; text-align: center; color: white; font-weight: bold; font-size: 9pt; line-height: 18px;">
                    {progress_pct}%
                </div>
            </div>
        </div>

        <h3>Database Module Summary</h3>
        <table width="100%" cellpadding="6" style="font-size:10pt; border-collapse: collapse; border: 1px solid #ddd; margin-bottom: 16px;">
            <tr style="border-bottom: 1px solid #eee;">
                <td width="30%"><b>Project Name:</b></td>
                <td>{p_name}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Client:</b></td>
                <td>{p_client}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Design Standard:</b></td>
                <td>{p_standard}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Traffic Survey:</b></td>
                <td>{ta_summary}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Subgrade properties:</b></td>
                <td>{subgrade_summary}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Pavement Composition:</b></td>
                <td>{sd_summary}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Marshall Mix:</b></td>
                <td>{mix_summary}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>BOQ Estimate:</b></td>
                <td>{mq_summary}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Engineering Review:</b></td>
                <td><b>{rev_status}</b></td>
            </tr>
        </table>
        {override_html}
        """
        
        missing = []
        if not project.work_name or not project.client_id or not project.consultant or not project.report_id:
            missing.append("• Project metadata is incomplete (check Client, Consultant, and Report ID).")
        if status.get("traffic") != "complete":
            missing.append("• Traffic / MSA analysis has not been completed.")
        if project.subgrade_cbr is None or project.subgrade_mr is None:
            missing.append("• Subgrade CBR and Resilient Modulus (Mr) have not been set.")
        if status.get("structural") != "complete":
            missing.append("• Structural design has not been saved.")
        if not mq:
            missing.append("• Material Quantity / BOQ estimation has not been run.")
            
        if missing:
            html += "<p style='color:#b22222; margin-top:10px; font-weight:bold;'>Review Checklist Warnings:<br>" + "<br>".join(missing) + "</p>"
        else:
            html += "<p style='color:#1d7a3a; margin-top:10px; font-weight:bold;'>✔ All readiness validation checks passed! Ready for final ZIP submission packaging.</p>"
            
        self.lbl_readiness.setText(html)

    def _on_lock_toggle(self) -> None:
        if self._project_id is None:
            return

        p = self.db.get_project(self._project_id)
        if not p:
            return

        try:
            if p.locked:
                ans = QMessageBox.warning(
                    self,
                    "Unlock Design Confirmation",
                    "WARNING: Unlocking this design allows modification of key calculation parameters. "
                    "This will invalidate the locked snapshot audit trail.\n\n"
                    "Are you sure you want to unlock this project?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    self.db.unlock_project(self._project_id)
                    self.db.set_module_status(self._project_id, "submission", "empty")
                    QMessageBox.information(self, "Unlocked", "Design unlocked successfully.")
            else:
                # ENFORCE VALIDATION GATE
                from app.engineering.design_audit import check_validation_gate
                ok, gate_errors = check_validation_gate(self._project_id, self.db)
                if not ok:
                    err_txt = "\n".join(gate_errors)
                    QMessageBox.critical(
                        self,
                        "Validation Gate Blocked",
                        f"Project cannot be locked. The following validation gate criteria failed:\n\n{err_txt}"
                    )
                    return

                self.db.lock_project(self._project_id)
                self.db.set_module_status(self._project_id, "submission", "complete")
                QMessageBox.information(
                    self,
                    "Locked",
                    "Design locked successfully!\n\n"
                    "The current inputs, calculation parameters, and results are serialized "
                    "in the lock snapshot and protected from edits. You can create revision copies "
                    "or export submission ZIP packages next."
                )
            self._refresh()
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _on_create_revision(self) -> None:
        if self._project_id is None:
            return
        p = self.db.get_project(self._project_id)
        if not p or not p.locked:
            QMessageBox.warning(self, "Failed", "Project must be locked to create a revision copy.")
            return

        from app.core.branding import get_branding_profile
        brand = get_branding_profile()
        default_eng = brand.get("engineer_name") or p.submitted_by or ""

        dlg = RevisionCreationDialog(default_eng, self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_data()
        if not data["engineer"] or not data["description"]:
            QMessageBox.warning(self, "Invalid Inputs", "Engineer Name and Description of Change are required.")
            return

        note_dict = {
            "engineer": data["engineer"],
            "description": data["description"],
            "reason": data["reason"]
        }
        note_str = json.dumps(note_dict)

        try:
            new_pid = self.db.create_project_revision(self._project_id, note_str)
            QMessageBox.information(
                self,
                "Revision Created",
                f"New revision branch created successfully!\n\n"
                f"Active project switched to Revision #{p.revision_number + 1} (Project #{new_pid}).\n"
                f"This copy is unlocked and ready for edits."
            )
            self.project_changed.emit(new_pid)
        except Exception as e:
            QMessageBox.critical(self, "Revision failed", str(e))

    def _on_export_dpr(self) -> None:
        if self._project_id is None:
            return
        p = self.db.get_project(self._project_id)
        if not p:
            return

        # File picker to save Word document
        default_name = f"NH_DPR_Project_{self._project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Professional DPR Report",
            str(Path.home() / "Desktop" / default_name),
            "Word Documents (*.docx)"
        )
        if not path:
            return

        try:
            meta = {
                "project_title": p.work_name or "Pavement Report",
                "work_name": p.work_name or "",
                "work_order_no": p.work_order_no or "",
                "work_order_date": p.work_order_date or "",
                "client": (p.client.name if p.client else ""),
                "agency": p.agency or "",
                "submitted_by": p.submitted_by or "",
                "report_date": datetime.now().strftime("%d-%b-%Y"),
                "binder_grade": p.binder_grade or "",
                "mix_type_key": p.mix_type or "",
            }
            ctx = CombinedReportContext(**meta)
            
            build_combined_report(
                Path(path),
                self.db,
                self._project_id,
                ctx,
            )
            try:
                self.db.record_generated_file(self._project_id, Path(path).name)
            except Exception:
                pass
            QMessageBox.information(
                self,
                "Success",
                f"Professional DPR Report generated successfully!\n\n"
                f"File saved to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Report Generation Failed",
                f"Failed to compile report Word document: {e}"
            )

    def _on_export_zip(self) -> None:
        if self._project_id is None:
            return
        p = self.db.get_project(self._project_id)
        if not p:
            return

        if not p.locked:
            QMessageBox.warning(
                self,
                "Lock Required",
                "Project must be locked first to freeze parameters and establish the lock snapshot audit trail before final submission packaging."
            )
            return

        # 1. Compile final Word report to temporary folder
        temp_docx_path = Path(REPORTS_DIR) / f"temp_{self._project_id}_submission.docx"
        try:
            meta = {
                "project_title": p.work_name or "Pavement Report",
                "work_name": p.work_name or "",
                "work_order_no": p.work_order_no or "",
                "work_order_date": p.work_order_date or "",
                "client": (p.client.name if p.client else ""),
                "agency": p.agency or "",
                "submitted_by": p.submitted_by or "",
                "report_date": datetime.now().strftime("%d-%b-%Y"),
                "binder_grade": p.binder_grade or "",
                "mix_type_key": p.mix_type or "",
            }
            ctx = CombinedReportContext(**meta)
            
            build_combined_report(
                temp_docx_path,
                self.db,
                self._project_id,
                ctx,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Report Generation Failed",
                f"Failed to compile report Word document before archiving: {e}"
            )
            return

        # 2. File picker to save ZIP delivery package
        default_name = f"NH_Submission_Project_{self._project_id}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Final Submission Package",
            str(Path.home() / "Desktop" / default_name),
            "ZIP Archives (*.zip)"
        )
        if not path:
            if temp_docx_path.exists():
                temp_docx_path.unlink()
            return

        try:
            # FIX swapped arguments bug: report_path is temp_docx_path, archive_out_path is Path(path)
            generate_project_archive(self.db, self._project_id, temp_docx_path, Path(path))
            QMessageBox.information(
                self,
                "Success",
                f"Final submission package created successfully!\n\n"
                f"Archive saved to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Packaging Failed",
                f"Failed to generate submission ZIP archive: {e}"
            )
        finally:
            if temp_docx_path.exists():
                temp_docx_path.unlink()
