"""Project metadata form (new/edit)."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QSpinBox,
)

from app.core import BINDER_GRADES, MIX_SPECS, MIX_TYPES, PROPERTY_LABELS
from .common import PageHeader, Card, styled_button


class BinderPropertiesDialog(QDialog):
    """Edit the optional bitumen/emulsion test results for a project."""

    def __init__(self, grade_code: str, props: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Binder Properties — {grade_code}")
        self.setMinimumWidth(420)
        grade = BINDER_GRADES.get(grade_code)
        tests = grade.applicable_tests if grade else tuple(PROPERTY_LABELS.keys())
        props = props or {}

        lay = QVBoxLayout(self)
        info = QLabel(
            f"<b>{grade.full_name if grade else grade_code}</b><br>"
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Leave a field blank to omit it from the report."
            "</span>")
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        self._spins: dict[str, QDoubleSpinBox] = {}
        self._notes_edit: QTextEdit | None = None
        for key in tests:
            label = PROPERTY_LABELS.get(key, key.replace("_", " ").title())
            sp = QDoubleSpinBox()
            sp.setRange(0, 99999); sp.setDecimals(3); sp.setSpecialValueText(" ")
            sp.setValue(float(props.get(key, 0) or 0))
            self._spins[key] = sp
            form.addRow(label, sp)
        # Free-text custom notes
        notes = QTextEdit(); notes.setMaximumHeight(60)
        notes.setPlainText(props.get("_notes", ""))
        self._notes_edit = notes
        form.addRow("Notes / custom", notes)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def collect(self) -> dict:
        out: dict = {}
        for k, sp in self._spins.items():
            v = sp.value()
            if v > 0:
                out[k] = v
        notes = self._notes_edit.toPlainText().strip()
        if notes:
            out["_notes"] = notes
        return out


class ProjectForm(QWidget):
    saved = Signal(int)   # emits project_id

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PageHeader("Project Setup", "Project metadata and engineering parameters")
        self.btn_save = styled_button("Save Project")
        self.btn_save.clicked.connect(self._on_save)
        header.add_action(self.btn_save)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        card = Card()
        form = QFormLayout(card)
        form.setContentsMargins(20, 16, 20, 16)
        form.setLabelAlignment(Qt.AlignLeft)

        # Fields definition
        self.work_name = QLineEdit()
        self.client = QLineEdit()
        self.location = QLineEdit()
        
        self.road_category = QComboBox()
        for cat in ["NH / SH", "Expressway", "MDR", "ODR", "Village Road", "Urban Arterial", "Other"]:
            self.road_category.addItem(cat)
            
        self.highway_type = QComboBox()
        for hw in ["National Highway (NH)", "State Highway (SH)", "Major District Road (MDR)", "Other District Road (ODR)", "Village Road"]:
            self.highway_type.addItem(hw)
            
        self.carriageway = QComboBox()
        for cw in ["Single Lane", "Intermediate Lane", "Two-lane carriageway", "Multi-lane carriageway"]:
            self.carriageway.addItem(cw)
            
        self.design_standard = QComboBox()
        for std in ["IRC:37-2018", "IRC:37-2012", "AASHTO Guide"]:
            self.design_standard.addItem(std)
            
        self.design_life = QSpinBox()
        self.design_life.setRange(1, 50)
        self.design_life.setValue(15)
        self.design_life.setSuffix(" yr")
        
        self.consultant = QLineEdit()
        self.checked_by = QLineEdit()
        self.report_id = QLineEdit()
        
        self.project_date = QLineEdit()
        from datetime import datetime
        self.project_date.setText(datetime.now().strftime("%d-%b-%Y"))

        # Hidden fields for backward compatibility with tests/scripts
        self.mix_type = QComboBox()
        self.mix_type.addItem("— Not selected —", None)
        for key, spec in MIX_SPECS.items():
            self.mix_type.addItem(f"{key} — {spec.name}", key)
        self.binder_grade = QComboBox()
        self.binder_grade.addItem("— Not selected —", None)
        for code, b in BINDER_GRADES.items():
            self.binder_grade.addItem(f"{code} — {b.full_name}", code)
        self._binder_props: dict = {}
        self.btn_binder_props = QPushButton("Edit Properties…")

        # Form layout assignment (No Mix Type or Binder Grade shown here)
        form.addRow("Project Name", self.work_name)
        form.addRow("Client Name", self.client)
        form.addRow("Location", self.location)
        form.addRow("Road Category", self.road_category)
        form.addRow("Highway Type", self.highway_type)
        form.addRow("Carriageway", self.carriageway)
        form.addRow("Design Standard", self.design_standard)
        form.addRow("Design Life", self.design_life)
        form.addRow("Consultant Name", self.consultant)
        form.addRow("Checked By", self.checked_by)
        form.addRow("Report ID", self.report_id)
        form.addRow("Date", self.project_date)

        body_layout.addWidget(card)
        body_layout.addStretch(1)
        layout.addWidget(body, stretch=1)

    def load_project(self, project_id: int | None) -> None:
        self._project_id = project_id
        self._binder_props = {}
        if project_id is None:
            self.work_name.clear()
            self.client.clear()
            self.location.clear()
            self.road_category.setCurrentIndex(0)
            self.highway_type.setCurrentIndex(0)
            self.carriageway.setCurrentIndex(2)
            self.design_standard.setCurrentIndex(0)
            self.design_life.setValue(15)
            self.consultant.clear()
            self.checked_by.clear()
            self.report_id.clear()
            from datetime import datetime
            self.project_date.setText(datetime.now().strftime("%d-%b-%Y"))
            self.mix_type.setCurrentIndex(0)
            self.binder_grade.setCurrentIndex(0)
            self._set_enabled(True)
            return

        p = self.db.get_project(project_id)
        if not p:
            return
        self.work_name.setText(p.work_name or "")
        self.location.setText(p.location or "")
        
        ridx = self.road_category.findText(p.road_category or "NH / SH")
        self.road_category.setCurrentIndex(ridx if ridx >= 0 else 0)
        
        hidx = self.highway_type.findText(p.highway_type or "")
        self.highway_type.setCurrentIndex(hidx if hidx >= 0 else 0)
        
        cidx = self.carriageway.findText(p.carriageway or "Two-lane carriageway")
        self.carriageway.setCurrentIndex(cidx if cidx >= 0 else 2)
        
        sidx = self.design_standard.findText(p.design_standard or "IRC:37-2018")
        self.design_standard.setCurrentIndex(sidx if sidx >= 0 else 0)
        
        self.design_life.setValue(int(p.design_life) if p.design_life is not None else 15)
        self.consultant.setText(p.consultant or "")
        self.checked_by.setText(p.checked_by or "")
        self.report_id.setText(p.report_id or "")
        
        if p.project_date:
            self.project_date.setText(p.project_date)
        elif p.created_at:
            self.project_date.setText(p.created_at.strftime("%d-%b-%Y"))
        else:
            from datetime import datetime
            self.project_date.setText(datetime.now().strftime("%d-%b-%Y"))

        idx = self.mix_type.findData(p.mix_type)
        self.mix_type.setCurrentIndex(idx if idx >= 0 else 0)
        bidx = self.binder_grade.findData(p.binder_grade)
        self.binder_grade.setCurrentIndex(bidx if bidx >= 0 else 0)
        if p.binder_properties_json:
            try:
                self._binder_props = json.loads(p.binder_properties_json)
            except json.JSONDecodeError:
                self._binder_props = {}
        if p.client:
            self.client.setText(p.client.name)
        else:
            self.client.clear()
        self._set_enabled(not p.locked)

    def _set_enabled(self, enabled: bool) -> None:
        self.work_name.setEnabled(enabled)
        self.client.setEnabled(enabled)
        self.location.setEnabled(enabled)
        self.road_category.setEnabled(enabled)
        self.highway_type.setEnabled(enabled)
        self.carriageway.setEnabled(enabled)
        self.design_standard.setEnabled(enabled)
        self.design_life.setEnabled(enabled)
        self.consultant.setEnabled(enabled)
        self.checked_by.setEnabled(enabled)
        self.report_id.setEnabled(enabled)
        self.project_date.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    def _edit_binder_props(self) -> None:
        code = self.binder_grade.currentData()
        if not code:
            self._binder_props = {}
            return
        dlg = BinderPropertiesDialog(code, self._binder_props, self)
        if dlg.exec() == QDialog.Accepted:
            self._binder_props = dlg.collect()

    def _on_save(self) -> None:
        data = {
            "work_name": self.work_name.text().strip() or "(Untitled)",
            "location": self.location.text().strip(),
            "road_category": self.road_category.currentText(),
            "highway_type": self.highway_type.currentText(),
            "carriageway": self.carriageway.currentText(),
            "design_standard": self.design_standard.currentText(),
            "design_life": self.design_life.value(),
            "consultant": self.consultant.text().strip(),
            "checked_by": self.checked_by.text().strip(),
            "report_id": self.report_id.text().strip(),
            "project_date": self.project_date.text().strip(),
        }
        # In new project setup, keep binder and mix type from hidden fields if set programmatically
        if self.mix_type.currentData():
            data["mix_type"] = self.mix_type.currentData()
        if self.binder_grade.currentData():
            data["binder_grade"] = self.binder_grade.currentData()
            if self._binder_props:
                data["binder_properties_json"] = json.dumps(self._binder_props)

        client_name = self.client.text().strip()
        if client_name:
            c = self.db.upsert_client(name=client_name)
            data["client_id"] = c.id
        if self._project_id is None:
            p = self.db.create_project(**data)
            self._project_id = p.id
        else:
            self.db.update_project(self._project_id, **data)
        self.saved.emit(self._project_id)

    def project_id(self) -> int | None:
        return self._project_id
