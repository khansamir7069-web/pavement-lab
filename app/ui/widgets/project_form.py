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
)

from app.core import BINDER_GRADES, MIX_SPECS, PROPERTY_LABELS
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

        header = PageHeader("Project", "Project metadata and materials")
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

        self.work_name = QLineEdit()
        self.work_order_no = QLineEdit()
        self.work_order_date = QLineEdit()
        self.client = QLineEdit()
        self.agency = QLineEdit()
        self.submitted_by = QLineEdit()
        self.mix_type = QComboBox()
        self.mix_type.addItem("— Not selected (set later in module) —", None)
        for key, spec in MIX_SPECS.items():
            self.mix_type.addItem(f"{key} — {spec.name}", key)

        # Binder grade combo + properties editor button
        self.binder_grade = QComboBox()
        self.binder_grade.addItem("— Not selected —", None)
        for code, b in BINDER_GRADES.items():
            self.binder_grade.addItem(f"{code} — {b.full_name}", code)
        self._binder_props: dict = {}

        binder_row = QHBoxLayout()
        binder_row.addWidget(self.binder_grade, stretch=1)
        self.btn_binder_props = QPushButton("Edit Properties…")
        self.btn_binder_props.setProperty("class", "Secondary")
        self.btn_binder_props.clicked.connect(self._edit_binder_props)
        binder_row.addWidget(self.btn_binder_props)

        form.addRow("Mix Type (optional)", self.mix_type)
        form.addRow("Binder Grade (optional)", binder_row)
        form.addRow("Name of Work", self.work_name)
        form.addRow("Work Order No.", self.work_order_no)
        form.addRow("Work Order Date", self.work_order_date)
        form.addRow("Client", self.client)
        form.addRow("Agency", self.agency)
        form.addRow("Submitted By", self.submitted_by)

        body_layout.addWidget(card)
        body_layout.addStretch(1)
        layout.addWidget(body, stretch=1)

    def load_project(self, project_id: int | None) -> None:
        self._project_id = project_id
        self._binder_props = {}
        if project_id is None:
            self.work_name.clear()
            self.work_order_no.clear()
            self.work_order_date.clear()
            self.client.clear()
            self.agency.clear()
            self.submitted_by.clear()
            self.mix_type.setCurrentIndex(0)
            self.binder_grade.setCurrentIndex(0)
            return
        p = self.db.get_project(project_id)
        if not p:
            return
        self.work_name.setText(p.work_name or "")
        self.work_order_no.setText(p.work_order_no or "")
        self.work_order_date.setText(p.work_order_date or "")
        self.agency.setText(p.agency or "")
        self.submitted_by.setText(p.submitted_by or "")
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
            "work_order_no": self.work_order_no.text().strip(),
            "work_order_date": self.work_order_date.text().strip(),
            "agency": self.agency.text().strip(),
            "submitted_by": self.submitted_by.text().strip(),
            "mix_type": self.mix_type.currentData() or "",   # "" = not selected
            "binder_grade": self.binder_grade.currentData() or None,
            "binder_properties_json": (
                json.dumps(self._binder_props) if self._binder_props else None
            ),
        }
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
