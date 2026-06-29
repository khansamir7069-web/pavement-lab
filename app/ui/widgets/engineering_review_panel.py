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
    QGridLayout,
    QFrame,
)

from .common import Card, PageHeader, styled_button
from app.engineering.design_audit import run_project_audit, AuditResult, AuditFinding

class EngineeringReviewPanel(QWidget):
    """Stage 9 Engineering Review panel."""

    saved = Signal(int)
    navigate_to = Signal(str)

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

        # Final Recommendation Banner
        self.rec_banner = QLabel("VALIDATION PENDING")
        self.rec_banner.setAlignment(Qt.AlignCenter)
        self.rec_banner.setStyleSheet(
            "background: #7f8c8d; color: white; font-weight: bold; font-size: 13pt; "
            "padding: 12px; border-radius: 4px; border: 1px solid #7f8c8d;"
        )
        bl.addWidget(self.rec_banner)

        # Score Cards Card
        score_card = Card()
        score_layout = QVBoxLayout(score_card)
        score_layout.setContentsMargins(20, 16, 20, 16)
        score_layout.setSpacing(10)
        
        score_title = QLabel("<b>Engineering Sub-Score Breakdown</b>")
        score_title.setStyleSheet("font-size: 11pt; color: #1f3a68;")
        score_layout.addWidget(score_title)
        
        self.score_grid = QGridLayout()
        self.score_grid.setSpacing(10)
        
        # We will dynamically create the 6 score cards in _update_scores
        score_layout.addLayout(self.score_grid)
        bl.addWidget(score_card)

        # Module Status Grid Card
        mod_card = Card()
        mod_layout = QVBoxLayout(mod_card)
        mod_layout.setContentsMargins(20, 16, 20, 16)
        mod_layout.setSpacing(10)
        
        mod_title = QLabel("<b>Module Quality Gate Status</b>")
        mod_title.setStyleSheet("font-size: 11pt; color: #1f3a68;")
        mod_layout.addWidget(mod_title)
        
        self.mod_statuses_layout = QHBoxLayout()
        self.mod_statuses_layout.setSpacing(12)
        mod_layout.addLayout(self.mod_statuses_layout)
        bl.addWidget(mod_card)

        # Cross-Module Consistency Table Card
        cm_card = Card()
        cm_layout = QVBoxLayout(cm_card)
        cm_layout.setContentsMargins(20, 16, 20, 16)
        cm_layout.setSpacing(10)
        
        cm_title = QLabel("<b>Cross-Module Parameter Alignment</b>")
        cm_title.setStyleSheet("font-size: 11pt; color: #1f3a68;")
        cm_layout.addWidget(cm_title)
        
        self.cm_table = QTableWidget()
        self.cm_table.setColumnCount(5)
        self.cm_table.setHorizontalHeaderLabels([
            "Module Comparison", "Parameter Field", "Source Module Value", "Target Module Value", "Status"
        ])
        self.cm_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cm_table.setMinimumHeight(150)
        cm_layout.addWidget(self.cm_table)
        bl.addWidget(cm_card)

        # Expert Audit Card (Issue List)
        self.audit_card = Card()
        audit_layout = QVBoxLayout(self.audit_card)
        audit_layout.setContentsMargins(20, 16, 20, 16)
        audit_layout.setSpacing(12)

        audit_header = QHBoxLayout()
        audit_title = QLabel("<b>Outstanding Design Validation Issues</b>")
        audit_title.setStyleSheet("font-size: 11pt; color: #1f3a68;")
        audit_header.addWidget(audit_title)
        
        self.btn_run_audit = QPushButton("Run Validation Check")
        self.btn_run_audit.setProperty("class", "Secondary")
        self.btn_run_audit.clicked.connect(self._run_audit)
        audit_header.addWidget(self.btn_run_audit)
        
        self.btn_export_audit = QPushButton("Export Summary Report")
        self.btn_export_audit.setProperty("class", "Secondary")
        self.btn_export_audit.clicked.connect(self._export_audit)
        audit_header.addWidget(self.btn_export_audit)
        
        audit_layout.addLayout(audit_header)

        # Findings table
        self.findings_table = QTableWidget()
        self.findings_table.setColumnCount(5)
        self.findings_table.setHorizontalHeaderLabels(["Severity", "Module", "Issue Description", "Suggested Action", "Navigation"])
        self.findings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.findings_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.findings_table.setMinimumHeight(220)
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

    def _go_to_module(self, key: str) -> None:
        mapping = {
            "Traffic": "traffic",
            "Subgrade": "subgrade",
            "Structural Design": "structural",
            "IITPAVE Status": "iitpave_status",
            "Mix Design": "inputs",
            "BOQ": "material_qty",
            "Submission Center": "submission",
        }
        target = mapping.get(key)
        if target:
            self.navigate_to.emit(target)
        else:
            QMessageBox.warning(self, "Navigation Error", "Module navigation unavailable.")

    def _clear_grid_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _run_audit(self) -> None:
        if self._project_id is None:
            self.rec_banner.setText("VALIDATION PENDING")
            self.rec_banner.setStyleSheet("background: #7f8c8d; color: white; padding: 12px; border-radius: 4px;")
            self._clear_grid_layout(self.score_grid)
            self.findings_table.setRowCount(0)
            self.cm_table.setRowCount(0)
            return
        
        # Run audit calculation
        res = run_project_audit(self._project_id, self.db)
        
        # Persist validation results
        try:
            self.db.save_project_validation_results(self._project_id, res.to_dict())
        except Exception:
            pass

        # 1. Update Recommendation Banner
        rec_colors = {
            "READY FOR CONSULTANCY SUBMISSION": "background: #27ae60; border: 1px solid #219653; color: white;",
            "READY AFTER MINOR CORRECTIONS": "background: #f39c12; border: 1px solid #d35400; color: white;",
            "NOT READY FOR SUBMISSION": "background: #c0392b; border: 1px solid #962d22; color: white;"
        }
        self.rec_banner.setText(f"{res.final_recommendation}\n(Checked: {res.timestamp})")
        self.rec_banner.setStyleSheet(
            f"font-weight: bold; font-size: 12pt; padding: 12px; border-radius: 4px; "
            f"{rec_colors.get(res.final_recommendation, 'background:#7f8c8d; color:white;')}"
        )

        # 2. Update Engineering Score Cards
        self._clear_grid_layout(self.score_grid)
        scores = [
            ("Completeness", res.completeness_score, res.completeness_explanation),
            ("Consistency", res.consistency_score, res.consistency_explanation),
            ("Mechanistic Validation", res.mechanistic_score, res.mechanistic_explanation),
            ("Documentation", res.documentation_score, res.documentation_explanation),
            ("Submission", res.submission_score, res.submission_explanation),
            ("Overall Status", res.score, f"Overall project health evaluated at {res.score}/100.")
        ]
        for idx, (label, val, desc) in enumerate(scores):
            row = idx // 3
            col = idx % 3
            
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            card.setStyleSheet(
                "background: #f8f9fa; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px;"
            )
            vlay = QVBoxLayout(card)
            vlay.setSpacing(4)
            vlay.setContentsMargins(6, 6, 6, 6)
            
            lbl_title = QLabel(f"<b>{label}</b>")
            lbl_title.setStyleSheet("font-size: 9pt; color: #4a5568;")
            vlay.addWidget(lbl_title)
            
            score_color = "#27ae60" if val >= 90 else ("#f39c12" if val >= 70 else "#c0392b")
            lbl_val = QLabel(f"<span style='font-size: 16pt; font-weight: bold; color: {score_color};'>{val}%</span>")
            vlay.addWidget(lbl_val)
            
            lbl_desc = QLabel(desc)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("font-size: 8pt; color: #718096;")
            vlay.addWidget(lbl_desc)
            
            self.score_grid.addWidget(card, row, col)

        # 3. Update Module Quality Gate Grid
        self._clear_layout(self.mod_statuses_layout)
        for mod, status in (res.module_statuses or {}).items():
            btn = QPushButton(f"{mod.title()}: {status}")
            btn.setEnabled(False)
            if status == "PASS":
                btn.setStyleSheet(
                    "background: #d4edda; color: #155724; border: 1px solid #c3e6cb; "
                    "font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )
            elif status == "FAIL":
                btn.setStyleSheet(
                    "background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; "
                    "font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )
            else:
                btn.setStyleSheet(
                    "background: #fff3cd; color: #856404; border: 1px solid #ffeeba; "
                    "font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )
            self.mod_statuses_layout.addWidget(btn)

        # 4. Cross-Module Consistency Table
        checks = res.consistency_checks or []
        self.cm_table.setRowCount(len(checks))
        for idx, check in enumerate(checks):
            item_mod = QTableWidgetItem(check["module"])
            item_mod.setTextAlignment(Qt.AlignCenter)
            self.cm_table.setItem(idx, 0, item_mod)
            
            item_fld = QTableWidgetItem(check["field"])
            item_fld.setTextAlignment(Qt.AlignCenter)
            self.cm_table.setItem(idx, 1, item_fld)
            
            item_src = QTableWidgetItem(check["source_val"])
            item_src.setTextAlignment(Qt.AlignCenter)
            self.cm_table.setItem(idx, 2, item_src)
            
            item_tgt = QTableWidgetItem(check["target_val"])
            item_tgt.setTextAlignment(Qt.AlignCenter)
            self.cm_table.setItem(idx, 3, item_tgt)
            
            item_st = QTableWidgetItem(check["status"])
            item_st.setTextAlignment(Qt.AlignCenter)
            st_color = "#27ae60" if check["status"] == "PASS" else "#c0392b"
            item_st.setForeground(QColor(st_color))
            self.cm_table.setItem(idx, 4, item_st)

        # 5. Outstanding Issues Table
        self.findings_table.setRowCount(len(res.findings))
        for i, f in enumerate(res.findings):
            item_sev = QTableWidgetItem(f.severity.upper())
            sev_colors = {
                "critical": "#c0392b",
                "major": "#e67e22",
                "warning": "#f39c12",
                "info": "#27ae60"
            }
            item_sev.setForeground(QColor(sev_colors.get(f.severity, "#333333")))
            item_sev.setTextAlignment(Qt.AlignCenter)
            self.findings_table.setItem(i, 0, item_sev)
            
            item_mod = QTableWidgetItem(f.module.title())
            item_mod.setTextAlignment(Qt.AlignCenter)
            self.findings_table.setItem(i, 1, item_mod)
            
            item_issue = QTableWidgetItem(f.issue)
            self.findings_table.setItem(i, 2, item_issue)
            
            rec_text = f"Recommendation: {f.recommendation}\nReason: {f.engineering_reason}"
            item_rec = QTableWidgetItem(rec_text)
            self.findings_table.setItem(i, 3, item_rec)
            
            # Go To Button
            btn_goto = QPushButton("Go To")
            btn_goto.setProperty("class", "Secondary")
            btn_goto.clicked.connect(lambda *_, k=f.navigation_key: self._go_to_module(k))
            self.findings_table.setCellWidget(i, 4, btn_goto)

    def _export_audit(self) -> None:
        if self._project_id is None:
            return
        from app.engineering.design_audit import run_project_audit
        res = run_project_audit(self._project_id, self.db)
        
        default = f"Validation_Report_Project_{self._project_id}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export Audit Summary", default, "Text Files (*.txt)")
        if not path:
            return
            
        try:
            lines = [
                "==================================================",
                "   ROADX DESIGN VALIDATION SUMMARY REPORT",
                "==================================================",
                f"Project ID: {self._project_id}",
                f"Validation Timestamp: {res.timestamp}",
                f"Final Recommendation: {res.final_recommendation}",
                f"Overall Engineering Score: {res.score}/100",
                f"Readiness Status: {res.readiness_status}",
                f"Risk Evaluation: {res.risk_level}",
                "--------------------------------------------------",
                "Score Card Breakdown:",
                f" - Completeness: {res.completeness_score}%",
                f" - Consistency: {res.consistency_score}%",
                f" - Mechanistic: {res.mechanistic_score}%",
                f" - Documentation: {res.documentation_score}%",
                f" - Submission: {res.submission_score}%",
                "--------------------------------------------------",
                "Module Status Grid:",
            ]
            for m, st in (res.module_statuses or {}).items():
                lines.append(f" - {m.title()}: {st}")
            lines.append("--------------------------------------------------")
            lines.append("Cross-Module Consistency Analysis:")
            for check in (res.consistency_checks or []):
                lines.append(f" - {check['module']} ({check['field']}): {check['source_val']} vs {check['target_val']} -> {check['status']}")
            lines.append("--------------------------------------------------")
            lines.append(f"Total Finding Warnings/Issues: {len(res.findings)}")
            lines.append("")
            
            for idx, f in enumerate(res.findings, 1):
                lines.append(f"{idx}. [{f.severity.upper()}] {f.module.upper()}")
                lines.append(f"   Issue: {f.issue}")
                lines.append(f"   Action: {f.recommendation}")
                lines.append(f"   Reason: {f.engineering_reason}")
                lines.append("")
                
            with open(path, "w", encoding="utf-8") as file:
                file.write("\n".join(lines))
                
            QMessageBox.information(self, "Export Successful", f"Audit report exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
