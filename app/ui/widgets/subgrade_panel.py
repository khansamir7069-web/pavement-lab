"""Subgrade evaluation panel — Stage 3.

Allows the user to input Subgrade CBR (%) and calculates/saves the Resilient Modulus (Mr) to the database.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .common import Card, PageHeader, styled_button

class SubgradePanel(QWidget):
    """Subgrade / CBR design panel."""

    saved = Signal(int)        # emits project_id after a successful save

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
            "Subgrade / CBR Evaluation",
            "IRC:37-2018 Annex E — Evaluate subgrade resilient modulus (Mr) from CBR"
        )
        self.btn_save = styled_button("Save Subgrade Info")
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

        # Inputs Card
        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)

        self.cbr = QDoubleSpinBox()
        self.cbr.setRange(0.5, 100.0)
        self.cbr.setValue(5.0)
        self.cbr.setDecimals(1)
        self.cbr.setSuffix(" %")
        self.cbr.valueChanged.connect(self._recalc_mr)

        self.mr_mpa = QDoubleSpinBox()
        self.mr_mpa.setRange(0.0, 1000.0)
        self.mr_mpa.setValue(0.0)
        self.mr_mpa.setDecimals(1)
        self.mr_mpa.setSpecialValueText(" (auto from CBR)")
        self.mr_mpa.setSuffix(" MPa")
        self.mr_mpa.valueChanged.connect(self._recalc_mr)

        self.lbl_auto_mr = QLabel("")
        self.lbl_auto_mr.setStyleSheet("font-size:11pt; font-weight:bold; color:#1d7a3a;")

        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Enter soil type, compaction details, or field testing notes...")
        self.notes.setMaximumHeight(80)

        form.addRow("Subgrade CBR (4-day soaked)", self.cbr)
        form.addRow("Resilient Modulus (Mr) override", self.mr_mpa)
        form.addRow("", self.lbl_auto_mr)
        form.addRow("Soil Notes / Remarks", self.notes)
        bl.addWidget(in_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)
        
        self._recalc_mr()

    def _recalc_mr(self) -> None:
        cbr = self.cbr.value()
        val = self.mr_mpa.value()
        if val > 0:
            mr = val
            self.lbl_auto_mr.setText(f"Using manual Resilient Modulus (Mr): {mr:.1f} MPa")
        else:
            if cbr <= 5.0:
                mr = 10.0 * cbr
            else:
                mr = 17.6 * (cbr ** 0.64)
            self.lbl_auto_mr.setText(f"Computed Resilient Modulus (Mr): {mr:.1f} MPa")

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_save.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        p = self.db.get_project(pid)
        if p:
            self.cbr.blockSignals(True)
            self.mr_mpa.blockSignals(True)
            self.cbr.setValue(p.subgrade_cbr if p.subgrade_cbr is not None else 5.0)
            self.mr_mpa.setValue(p.subgrade_mr if p.subgrade_mr is not None else 0.0)
            self.cbr.blockSignals(False)
            self.mr_mpa.blockSignals(False)
        self._recalc_mr()
        self._set_enabled(not (p.locked if p else False))

    def _set_enabled(self, enabled: bool) -> None:
        self.cbr.setEnabled(enabled)
        self.mr_mpa.setEnabled(enabled)
        self.notes.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    def _on_save(self) -> None:
        if self._project_id is None:
            return
        cbr = self.cbr.value()
        val = self.mr_mpa.value()
        if val > 0:
            mr = val
        else:
            if cbr <= 5.0:
                mr = 10.0 * cbr
            else:
                mr = 17.6 * (cbr ** 0.64)

        try:
            self.db.update_project(self._project_id, subgrade_cbr=cbr, subgrade_mr=mr)
            self.db.set_module_status(self._project_id, "subgrade", "complete")
            QMessageBox.information(
                self, "Subgrade Saved",
                "Subgrade completed.\n\nNext Step:\nGenerate pavement design options."
            )
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
