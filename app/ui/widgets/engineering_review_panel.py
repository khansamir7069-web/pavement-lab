"""Engineering Review panel — Stage 9.

Allows reviewer to complete checks, verification statuses, and notes.
"""
from __future__ import annotations

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
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

    def _set_enabled(self, enabled: bool) -> None:
        self.cb_design_review.setEnabled(enabled)
        self.cb_input_verification.setEnabled(enabled)
        self.cb_traffic_verification.setEnabled(enabled)
        self.cb_material_verification.setEnabled(enabled)
        self.iitpave_status.setEnabled(enabled)
        self.txt_notes.setEnabled(enabled)
        # Allow saving & updating review_status even if locked
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
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
