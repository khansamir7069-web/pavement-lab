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
        
        # Calculate completion %
        completed_count = 0
        total_modules = 5
        
        has_traffic = status.get("traffic") == "complete"
        if has_traffic:
            completed_count += 1
            
        has_subgrade = project.subgrade_cbr is not None and project.subgrade_cbr > 0.0
        if has_subgrade:
            completed_count += 1
            
        has_structural = status.get("structural") == "complete"
        if has_structural:
            completed_count += 1
            
        mech_val = self.db.latest_mechanistic_validation(project.id)
        has_iitpave = mech_val is not None and not mech_val.refused
        if has_iitpave:
            completed_count += 1
            
        mq_row = self.db.latest_material_quantity(project.id)
        has_boq = mq_row is not None
        if has_boq:
            completed_count += 1
            
        progress_pct = int((completed_count / total_modules) * 100)

        # Audit Status
        audit_status = "Not Run"
        audit_color = "#6a7180"
        try:
            from app.engineering.design_audit import run_project_audit
            audit = run_project_audit(project.id, self.db)
            audit_status = f"{audit.readiness_status} (Score: {audit.score}/100, Risk: {audit.risk_level})"
            if audit.risk_level == "GREEN":
                audit_color = "#1d7a3a"
            elif audit.risk_level == "YELLOW":
                audit_color = "#b28a00"
            else:
                audit_color = "#b22222"
        except Exception:
            pass
            
        boq_status = "Complete" if has_boq else "Incomplete"
        boq_color = "#1d7a3a" if has_boq else "#b22222"
        
        dpr_status = "Ready for Export" if (has_traffic and has_structural) else "Incomplete (Traffic and Structural design required)"
        dpr_color = "#1d7a3a" if (has_traffic and has_structural) else "#b22222"
        
        html = f"""
        <table width="100%" cellpadding="4" style="font-size:10pt; border-collapse: collapse;">
            <tr style="border-bottom: 1px solid #eee;">
                <td width="35%"><b>Workflow Completion:</b></td>
                <td>
                    <div style="background-color: #e0e0e0; border-radius: 4px; width: 100%; height: 16px;">
                        <div style="background-color: #2980b9; border-radius: 4px; width: {progress_pct}%; height: 16px; text-align: center; color: white; font-weight: bold; font-size: 8pt; line-height: 16px;">
                            {progress_pct}%
                        </div>
                    </div>
                </td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>Design Audit Status:</b></td>
                <td style="color: {audit_color}; font-weight: bold;">{audit_status}</td>
            </tr>
            <tr style="border-bottom: 1px solid #eee;">
                <td><b>BOQ / Costing Status:</b></td>
                <td style="color: {boq_color}; font-weight: bold;">{boq_status}</td>
            </tr>
            <tr>
                <td><b>DPR Report Status:</b></td>
                <td style="color: {dpr_color}; font-weight: bold;">{dpr_status}</td>
            </tr>
        </table>
        """
        
        missing = []
        if not project.work_name or not project.client_id or not project.consultant or not project.report_id:
            missing.append("• Project metadata is incomplete (check Client, Consultant, and Report ID).")
        if not has_traffic:
            missing.append("• Traffic / MSA analysis has not been completed.")
        if not has_subgrade:
            missing.append("• Subgrade CBR and Resilient Modulus (Mr) have not been set.")
        if not has_structural:
            missing.append("• Structural design has not been saved.")
        if not has_boq:
            missing.append("• Material Quantity / BOQ estimation has not been run.")
        if not has_iitpave:
            missing.append("• IITPAVE mechanistic check has not been run.")
            
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
