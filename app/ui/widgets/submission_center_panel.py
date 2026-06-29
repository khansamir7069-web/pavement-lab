"""Submission Center UI Panel.

Provides engineer checklists, project readiness, final design locking,
revision creation, and zip packaging export.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import REPORTS_DIR
from app.reports.report_builder import build_combined_report, CombinedReportContext
from app.core.project_archive import generate_project_archive
from .common import PageHeader, Card, styled_button


class SubmissionCenterPanel(QWidget):
    saved = Signal(int)             # Emits project_id
    project_changed = Signal(int)   # Emits project_id when revision created

    def __init__(self, db: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "Submission Center", "Consultancy review checklists, project locking & package delivery"
        )
        self.btn_save_checklist = styled_button("Save Checklist & Review Info")
        self.btn_save_checklist.clicked.connect(self._on_save_checklist)
        self.header.add_action(self.btn_save_checklist)
        lay.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(14)

        # 1. Project Info & Metadata
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

        # 3. Project Readiness Card
        self.readiness_card = Card()
        rl = QVBoxLayout(self.readiness_card)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(8)
        rl.addWidget(QLabel("<b>Project Readiness Checklist</b>"))
        self.lbl_readiness = QLabel("Loading readiness checks...")
        self.lbl_readiness.setWordWrap(True)
        rl.addWidget(self.lbl_readiness)
        bl.addWidget(self.readiness_card)

        # 4. Review Workflow Form Card
        self.form_card = Card()
        form = QFormLayout(self.form_card)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)

        form.addRow(QLabel("<b>Engineering Review Workflow Checklists</b>"))

        self.cb_design_review = QCheckBox("Design review checklist verified (all standards checked)")
        self.cb_input_verification = QCheckBox("Inputs verified against site tests & soil reports")
        self.cb_traffic_verification = QCheckBox("Traffic projection assumptions verified")
        self.cb_material_verification = QCheckBox("Material property & tier assumptions verified")
        
        form.addRow("", self.cb_design_review)
        form.addRow("", self.cb_input_verification)
        form.addRow("", self.cb_traffic_verification)
        form.addRow("", self.cb_material_verification)

        self.iitpave_status = QComboBox()
        self.iitpave_status.addItems([
            "Not Verified",
            "Mechanistically Verified Design",
            "IRC Catalogue Design (Decision Support Mode)"
        ])
        form.addRow("IITPAVE Verification Status", self.iitpave_status)

        self.review_status = QComboBox()
        self.review_status.addItems([
            "Draft",
            "Under Review",
            "Reviewed",
            "Approved for Submission"
        ])
        form.addRow("Review/Submission Status", self.review_status)

        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Enter reviewer notes, observations, or sign-off remarks...")
        self.txt_notes.setMaximumHeight(80)
        form.addRow("Reviewer Notes & Remarks", self.txt_notes)

        bl.addWidget(self.form_card)

        # 5. Export Delivery Package Card
        export_card = Card()
        el = QHBoxLayout(export_card)
        el.setContentsMargins(16, 12, 16, 12)
        v_el = QVBoxLayout()
        v_el.addWidget(QLabel("<b>ZIP Delivery Package</b>"))
        v_el.addWidget(QLabel(
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Compiles Word report, inputs JSON, IITPAVE logs, summaries, "
            "and sign-off templates with disclaimers into a single ZIP."
            "</span>"
        ))
        el.addLayout(v_el)

        self.btn_export_zip = styled_button("Export Package (.zip)")
        self.btn_export_zip.clicked.connect(self._on_export_zip)
        el.addWidget(self.btn_export_zip)

        bl.addWidget(export_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll)

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self.btn_save_checklist.setEnabled(pid is not None)
        self.btn_export_zip.setEnabled(pid is not None)

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
            self._set_form_enabled(False)
        else:
            self.lbl_lock_state.setText("<b>Lock Status: Unlocked</b>")
            self.lbl_lock_state.setStyleSheet("font-size:12pt; color:#1d7a3a;")
            self.lbl_lock_details.setText("Project calculations and parameters can be modified.")
            self.btn_lock_toggle.setText("Lock Design")
            self.btn_create_revision.setEnabled(False)
            self._set_form_enabled(True)

        # Load checklist data
        self.review_status.setCurrentText(p.review_status or "Draft")
        checklist_dict = {}
        if p.checklist_json:
            try:
                checklist_dict = json.loads(p.checklist_json)
            except Exception:
                pass

        self.cb_design_review.setChecked(bool(checklist_dict.get("design_review", False)))
        self.cb_input_verification.setChecked(bool(checklist_dict.get("input_verification", False)))
        self.cb_traffic_verification.setChecked(bool(checklist_dict.get("traffic_verification", False)))
        self.cb_material_verification.setChecked(bool(checklist_dict.get("material_verification", False)))
        self.iitpave_status.setCurrentText(checklist_dict.get("iitpave_verification", "Not Verified"))
        self.txt_notes.setPlainText(checklist_dict.get("reviewer_notes", ""))

        # Compute readiness
        self._check_readiness(p)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.cb_design_review.setEnabled(enabled)
        self.cb_input_verification.setEnabled(enabled)
        self.cb_traffic_verification.setEnabled(enabled)
        self.cb_material_verification.setEnabled(enabled)
        self.iitpave_status.setEnabled(enabled)
        self.txt_notes.setEnabled(enabled)
        # Note: review_status and Save button can still be edited/clicked even if locked,
        # so engineer can update review workflows.
        self.review_status.setEnabled(True)
        self.btn_save_checklist.setEnabled(True)

    def _check_readiness(self, project: Any) -> None:
        status = self.db.get_module_status(project.id) or {}
        
        checks = []
        missing = []

        # 1. Project Metadata
        if project.work_name and project.client_id and project.consultant and project.report_id:
            checks.append("✔ Project Metadata (Name, Client, Consultant, Report ID) complete.")
        else:
            missing.append("• Missing project metadata: ensure Client, Consultant, and Report ID are filled in the Project Form.")

        # 2. Mix Design
        if status.get("mix_design") == "complete":
            checks.append("✔ Bituminous Mix Design saved.")
        else:
            missing.append("• Mix Design has not been completed/saved.")

        # 3. Traffic Analysis
        if status.get("traffic") == "complete":
            checks.append("✔ Traffic / MSA calculations completed.")
        else:
            missing.append("• Traffic / MSA analysis has not been completed.")

        # 4. Structural Design
        if status.get("structural") == "complete":
            checks.append("✔ Structural design completed.")
        else:
            missing.append("• Flexible structural design has not been saved.")

        # 5. Stabilized Design (Optional but checked)
        if status.get("stabilized") == "complete":
            checks.append("✔ Stabilized CTB/CTS design completed.")

        # 6. IITPAVE Verification
        mech_val = self.db.latest_mechanistic_validation(project.id)
        if mech_val:
            checks.append(f"✔ Mechanistic validation recorded (Fatigue: {mech_val.fatigue_verdict}, Rutting: {mech_val.rutting_verdict}).")
        else:
            missing.append("• Mechanistic validation (IITPAVE check) has not been run or saved.")

        html = ""
        if checks:
            html += "<p style='color:#1d7a3a;'>" + "<br>".join(checks) + "</p>"
        if missing:
            html += "<p style='color:#b22222; font-weight:bold;'>Missing Checks / Recommendations:<br>" + "<br>".join(missing) + "</p>"
        else:
            html += "<p style='color:#1d7a3a; font-weight:bold;'>✔ All readiness validation checks passed! Ready for consultancy report packaging.</p>"

        self.lbl_readiness.setText(html)

    def _collect_checklist(self) -> dict:
        return {
            "design_review": self.cb_design_review.isChecked(),
            "input_verification": self.cb_input_verification.isChecked(),
            "traffic_verification": self.cb_traffic_verification.isChecked(),
            "material_verification": self.cb_material_verification.isChecked(),
            "iitpave_verification": self.iitpave_status.currentText(),
            "reviewer_notes": self.txt_notes.toPlainText().strip(),
        }

    def _on_save_checklist(self) -> None:
        if self._project_id is None:
            return
        try:
            checklist = self._collect_checklist()
            status = self.review_status.currentText()
            self.db.save_project_checklist(self._project_id, status, checklist)
            QMessageBox.information(self, "Saved", "Checklist and workflow status saved successfully.")
            self._refresh()
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _on_lock_toggle(self) -> None:
        if self._project_id is None:
            return

        p = self.db.get_project(self._project_id)
        if not p:
            return

        try:
            if p.locked:
                # Warning before unlocking
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
                    QMessageBox.information(self, "Unlocked", "Design unlocked successfully.")
            else:
                # Save checklist first
                checklist = self._collect_checklist()
                status = self.review_status.currentText()
                self.db.save_project_checklist(self._project_id, status, checklist)
                
                # Lock project
                self.db.lock_project(self._project_id)
                QMessageBox.information(
                    self,
                    "Locked",
                    "Design locked successfully!\n\n"
                    "The current inputs, calculation parameters, and results are serialized "
                    "in the lock snapshot and protected from edits. You can create revision copies "
                    "if further adjustments are needed."
                )
            self._refresh()
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Lock Toggle Failed", str(e))

    def _on_create_revision(self) -> None:
        if self._project_id is None:
            return
        p = self.db.get_project(self._project_id)
        if not p or not p.locked:
            return

        from PySide6.QtWidgets import QInputDialog
        note, ok = QInputDialog.getText(
            self,
            "Create Revision",
            "Enter revision / modification note for the new revision clone:",
            QLineEdit.Normal,
            ""
        )
        if not ok or not note.strip():
            return

        try:
            new_pid = self.db.create_project_revision(self._project_id, note.strip())
            QMessageBox.information(
                self,
                "Revision Created",
                f"Revision project #{new_pid} successfully created.\n\n"
                "You have been navigated to the new revision clone."
            )
            self.project_changed.emit(new_pid)
        except Exception as e:
            QMessageBox.critical(self, "Revision Failed", str(e))

    def _on_export_zip(self) -> None:
        if self._project_id is None:
            return
            
        p = self.db.get_project(self._project_id)
        if not p:
            return

        # 1. Ask user to save docx report first or generate one dynamically to a temp file
        temp_docx_path = REPORTS_DIR / f"temp_combined_report_{self._project_id}.docx"
        try:
            # Build combined report context
            from app.ui.main_window import MainWindow
            # Since we need the meta details, we mock the context rehydration
            meta = {
                "project_title": p.work_name or "",
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
        default = REPORTS_DIR / f"SubmissionPackage_P{self._project_id}.zip"
        zip_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Submission Package ZIP",
            str(default),
            "ZIP Archive (*.zip)"
        )
        if not zip_path:
            # Cleanup temp file
            if temp_docx_path.is_file():
                temp_docx_path.unlink()
            return

        try:
            generate_project_archive(
                self.db,
                self._project_id,
                temp_docx_path,
                Path(zip_path)
            )
            QMessageBox.information(
                self,
                "Package Exported",
                f"Submission package successfully generated and saved to:\n{zip_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
        finally:
            # Cleanup temp file
            if temp_docx_path.is_file():
                temp_docx_path.unlink()
