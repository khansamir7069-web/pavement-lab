"""Engineering Review panel — Stage 9.

Allows reviewer to complete checks, verification statuses, and notes.
"""
from __future__ import annotations

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QFileDialog,
)

from .common import Card, PageHeader, styled_button

class EngineeringReviewPanel(QWidget):
    """Stage 9 Engineering Review panel."""

    saved = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "Engineering Review",
            "Consultancy review checklists, QA validation checks, and notes"
        )
        self.btn_save = styled_button("Save Review Checklist")
        self.btn_save.clicked.connect(self._on_save)
        self.header.add_action(self.btn_save)
        lay.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(14)

        # Project banner
        self.proj_banner = QLabel("⚠ No project loaded.")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;"
        )
        bl.addWidget(self.proj_banner)

        # Form Card
        form_card = Card()
        form = QFormLayout(form_card)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)

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
            "Mechanistic Verified Mode (Successful Run)",
            "Decision Support Mode (Stub/Inapplicable)"
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
        self.txt_notes.setMaximumHeight(100)
        form.addRow("Reviewer Notes & Remarks", self.txt_notes)

        bl.addWidget(form_card)

        # Expert Audit Card
        self.audit_card = Card()
        audit_layout = QVBoxLayout(self.audit_card)
        audit_layout.setContentsMargins(20, 16, 20, 16)
        audit_layout.setSpacing(12)

        audit_header = QHBoxLayout()
        audit_title = QLabel("<b>Expert Design Audit Summary</b>")
        audit_title.setStyleSheet("font-size: 11pt; color: #1f3a68;")
        audit_header.addWidget(audit_title)
        
        self.btn_run_audit = QPushButton("Run Audit")
        self.btn_run_audit.setProperty("class", "Secondary")
        self.btn_run_audit.clicked.connect(self._run_audit)
        audit_header.addWidget(self.btn_run_audit)
        
        self.btn_export_audit = QPushButton("Export Audit Summary")
        self.btn_export_audit.setProperty("class", "Secondary")
        self.btn_export_audit.clicked.connect(self._export_audit)
        audit_header.addWidget(self.btn_export_audit)
        
        audit_layout.addLayout(audit_header)

        # Status row
        status_layout = QHBoxLayout()
        self.lbl_audit_score = QLabel("Engineering Score: N/A")
        self.lbl_audit_score.setStyleSheet("font-size: 10pt; font-weight: bold;")
        self.lbl_risk_level = QLabel("Risk Level: N/A")
        self.lbl_risk_level.setStyleSheet("font-size: 10pt; font-weight: bold;")
        self.lbl_readiness_status = QLabel("Readiness Status: N/A")
        self.lbl_readiness_status.setStyleSheet("font-size: 10pt; font-weight: bold;")
        
        status_layout.addWidget(self.lbl_audit_score)
        status_layout.addWidget(self.lbl_risk_level)
        status_layout.addWidget(self.lbl_readiness_status)
        audit_layout.addLayout(status_layout)

        # Findings table
        self.findings_table = QTableWidget()
        self.findings_table.setColumnCount(4)
        self.findings_table.setHorizontalHeaderLabels(["Severity", "Module", "Issue", "Recommendation & Reason"])
        self.findings_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.findings_table.setMinimumHeight(200)
        audit_layout.addWidget(self.findings_table)

        bl.addWidget(self.audit_card)
        bl.addStretch(1)

        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_save.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        
        p = self.db.get_project(pid)
        if not p:
            return

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

        self._set_enabled(not p.locked)
        self._run_audit()

    def _set_enabled(self, enabled: bool) -> None:
        self.cb_design_review.setEnabled(enabled)
        self.cb_input_verification.setEnabled(enabled)
        self.cb_traffic_verification.setEnabled(enabled)
        self.cb_material_verification.setEnabled(enabled)
        self.iitpave_status.setEnabled(enabled)
        self.txt_notes.setEnabled(enabled)
        self.review_status.setEnabled(True)
        self.btn_save.setEnabled(True)

    def _collect_checklist(self) -> dict:
        return {
            "design_review": self.cb_design_review.isChecked(),
            "input_verification": self.cb_input_verification.isChecked(),
            "traffic_verification": self.cb_traffic_verification.isChecked(),
            "material_verification": self.cb_material_verification.isChecked(),
            "iitpave_verification": self.iitpave_status.currentText(),
            "reviewer_notes": self.txt_notes.toPlainText().strip(),
        }

    def _on_save(self) -> None:
        if self._project_id is None:
            return
        try:
            checklist = self._collect_checklist()
            status = self.review_status.currentText()
            self.db.save_project_checklist(self._project_id, status, checklist)
            self.db.set_module_status(self._project_id, "engineering_review", "complete")
            QMessageBox.information(self, "Saved", "Checklist and workflow status saved successfully.")
            self.saved.emit(self._project_id)
            self._run_audit()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _run_audit(self) -> None:
        if self._project_id is None:
            # Clear UI elements
            self.lbl_audit_score.setText("Engineering Score: N/A")
            self.lbl_risk_level.setText("Risk Level: N/A")
            self.lbl_readiness_status.setText("Readiness Status: N/A")
            self.findings_table.setRowCount(0)
            return
        
        from app.engineering.design_audit import run_project_audit
        res = run_project_audit(self._project_id, self.db)
        
        self.lbl_audit_score.setText(f"Engineering Score: {res.score}/100")
        
        color_map = {
            "GREEN": "#1d7a3a",
            "YELLOW": "#b56900",
            "RED": "#c22d2d"
        }
        color = color_map.get(res.risk_level, "#333333")
        self.lbl_risk_level.setText(f"Risk Level: <span style='color:{color}; font-weight:bold;'>{res.risk_level}</span>")
        self.lbl_readiness_status.setText(f"Readiness Status: {res.readiness_status}")
        
        self.findings_table.setRowCount(len(res.findings))
        for i, f in enumerate(res.findings):
            item_sev = QTableWidgetItem(f.severity.upper())
            sev_colors = {
                "critical": "#c22d2d",
                "warning": "#b56900",
                "info": "#1d7a3a"
            }
            item_sev.setForeground(QColor(sev_colors.get(f.severity, "#333333")))
            item_sev.setTextAlignment(Qt.AlignCenter)
            self.findings_table.setItem(i, 0, item_sev)
            
            item_mod = QTableWidgetItem(f.module.title())
            item_mod.setTextAlignment(Qt.AlignCenter)
            self.findings_table.setItem(i, 1, item_mod)
            
            self.findings_table.setItem(i, 2, QTableWidgetItem(f.issue))
            
            rec_text = f"Recommendation: {f.recommendation}\nReason: {f.engineering_reason}"
            item_rec = QTableWidgetItem(rec_text)
            self.findings_table.setItem(i, 3, item_rec)

    def _export_audit(self) -> None:
        if self._project_id is None:
            return
        from app.engineering.design_audit import run_project_audit
        res = run_project_audit(self._project_id, self.db)
        
        default = f"Audit_Summary_Project_{self._project_id}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export Audit Summary", default, "Text Files (*.txt)")
        if not path:
            return
            
        try:
            lines = [
                f"SAMPAVE DESIGN AUDIT SUMMARY REPORT",
                f"Project ID: {self._project_id}",
                f"Engineering Score: {res.score}/100",
                f"Risk Level: {res.risk_level}",
                f"Readiness Status: {res.readiness_status}",
                "==================================================",
                f"Total Findings: {len(res.findings)}",
                ""
            ]
            for idx, f in enumerate(res.findings, 1):
                lines.append(f"{idx}. [{f.severity.upper()}] in Module: {f.module.upper()}")
                lines.append(f"   Issue: {f.issue}")
                lines.append(f"   Recommendation: {f.recommendation}")
                lines.append(f"   Engineering Reason: {f.engineering_reason}")
                lines.append("")
                
            with open(path, "w", encoding="utf-8") as file:
                file.write("\n".join(lines))
                
            QMessageBox.information(self, "Export Successful", f"Audit summary exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
