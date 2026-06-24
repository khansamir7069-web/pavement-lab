"""Submission panel — Stage 10.

Handles project locking, revision creation, readiness checklist, and final delivery ZIP generation.
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
)

from app.config import REPORTS_DIR
from app.reports.report_builder import build_combined_report, CombinedReportContext
from app.core.project_archive import generate_project_archive
from .common import PageHeader, Card, styled_button

class SubmissionPanel(QWidget):
    """Stage 10 Submission Panel."""

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

        # 4. Export Delivery Package Card
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
        lay.addWidget(scroll, stretch=1)

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
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
        
        checks = []
        missing = []

        # 1. Project Metadata
        if project.work_name and project.client_id and project.consultant and project.report_id:
            checks.append("✔ Project Metadata (Name, Client, Consultant, Report ID) complete.")
        else:
            missing.append("• Missing project metadata: ensure Client, Consultant, and Report ID are filled.")

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

        # 5. Stabilized Design (Optional)
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
            html += "<p style='color:#1d7a3a; font-weight:bold;'>✔ All readiness validation checks passed! Ready for final ZIP submission packaging.</p>"

        self.lbl_readiness.setText(html)

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
                    self.db.set_module_status(self._project_id, "submission", "empty")
                    QMessageBox.information(self, "Unlocked", "Design unlocked successfully.")
            else:
                # Lock project
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

        ans = QMessageBox.question(
            self,
            "Create Revision Copy",
            "This will create a new editable branch/revision copy of the project. "
            "The locked snapshot of this version will remain archived for audit auditability.\n\n"
            "Do you want to create a revision branch now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if ans != QMessageBox.Yes:
            return

        try:
            new_proj = self.db.create_project_revision(self._project_id)
            QMessageBox.information(
                self,
                "Revision Created",
                f"New revision created!\n\n"
                f"Active project switched to Revision #{new_proj.revision_number} (Project #{new_proj.id}).\n"
                f"This copy is unlocked and ready for edits."
            )
            # Notify main window to reload and switch active project
            self.project_changed.emit(new_proj.id)
        except Exception as e:
            QMessageBox.critical(self, "Revision failed", str(e))

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
            # Clean up temp file
            if temp_docx_path.exists():
                temp_docx_path.unlink()
            return

        try:
            generate_project_archive(self.db, self._project_id, Path(path), temp_docx_path)
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
