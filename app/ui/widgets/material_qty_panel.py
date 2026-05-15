"""Material Quantity Calculator — Phase 7.

One-page form: a layer table where each row is a LayerInput. Compute
button aggregates tonnages; Save persists to MaterialQuantityDesign;
Export Word emits the BOQ section via the Phase-6 report layer.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    LAYER_TYPES,
    LayerInput,
    MaterialQuantityInput,
    MaterialQuantityResult,
    compute_material_quantity,
)
from app.core.material_quantity import (
    DEFAULT_BINDER_PCT,
    DEFAULT_DENSITY,
    DEFAULT_SPRAY_RATE_KGM2,
)
from .common import Card, PageHeader, styled_button


_HDRS = ["Layer", "Length (m)", "Width (m)", "Thickness (mm)",
        "Density (t/m³)", "Binder %", "Spray (kg/m²)", "Waste %"]


def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 2) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    sp.setMinimumWidth(80)
    return sp


def _make_layer_combo(default: str = "DBM") -> QComboBox:
    cb = QComboBox()
    for t in LAYER_TYPES:
        cb.addItem(t)
    cb.setCurrentText(default)
    return cb


class MaterialQuantityPanel(QWidget):
    """Independent BOQ panel."""

    saved = Signal(int)
    export_requested = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last_result: MaterialQuantityResult | None = None
        self._build()
        self._seed_default_rows()

    # ----- build -----
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Material Quantity Calculator",
            "Layer-wise tonnage & binder demand — MoRTH-500 / MoRTH-400 / IRC:111"
        )
        self.btn_add = styled_button("+ Add Layer", "secondary")
        self.btn_add.clicked.connect(lambda: self._add_row("DBM"))
        self.btn_remove = styled_button("− Remove", "secondary")
        self.btn_remove.clicked.connect(self._remove_selected_row)
        self.btn_compute = styled_button("Compute")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        self.btn_export = styled_button("Export Word", "secondary")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        for b in (self.btn_export, self.btn_save, self.btn_compute,
                  self.btn_remove, self.btn_add):
            self.header.add_action(b)
        lay.addWidget(self.header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(12)

        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;")
        bl.addWidget(self.proj_banner)

        # Input table
        in_card = Card()
        il = QVBoxLayout(in_card)
        il.setContentsMargins(16, 12, 16, 12); il.setSpacing(6)
        il.addWidget(QLabel("<b>Layers (BOQ rows)</b>"))
        self.tbl = QTableWidget(0, len(_HDRS))
        self.tbl.setHorizontalHeaderLabels(_HDRS)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        il.addWidget(self.tbl)
        il.addWidget(QLabel(
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Leave Density / Binder% / Spray blank to use the MoRTH default "
            "for the layer type. Sprayed coats (Prime / Tack) ignore "
            "thickness and density.</span>"))
        bl.addWidget(in_card)

        # Results
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(16, 12, 16, 12); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>Computed BOQ</b>"))
        self.lbl_totals = QLabel("Total: —")
        self.lbl_totals.setStyleSheet(
            "font-size:13pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_totals)
        self.res_tbl = QTableWidget(
            0, 5)
        self.res_tbl.setHorizontalHeaderLabels(
            ["Layer", "Area (m²)", "Layer (t)", "Binder (t)", "Reference"])
        self.res_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.res_tbl.verticalHeader().setVisible(False)
        rl.addWidget(self.res_tbl)
        self.lbl_notes = QLabel("")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        rl.addWidget(self.lbl_notes)
        self.res_card.setVisible(False)
        bl.addWidget(self.res_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    def _seed_default_rows(self) -> None:
        for lt in ("Prime Coat", "DBM", "Tack Coat", "BC"):
            self._add_row(lt)

    # ----- row helpers -----
    def _add_row(self, layer: str) -> None:
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        combo = _make_layer_combo(layer)
        self.tbl.setCellWidget(r, 0, combo)
        widgets = [
            _spin(1000.0, 0, 1e6, 50, 1),   # length
            _spin(3.5,    0, 50,  0.5, 2),  # width
            _spin(40.0,   0, 1000, 5, 1),   # thickness
            _spin(0.0,    0, 5,   0.05, 3), # density (0 = default)
            _spin(0.0,    0, 15,  0.1, 2),  # binder %
            _spin(0.0,    0, 5,   0.05, 3), # spray
            _spin(2.0,    0, 25,  0.5, 2),  # waste
        ]
        for c, w in enumerate(widgets, start=1):
            w.setSpecialValueText("(default)") if c in (4, 5, 6) else None
            self.tbl.setCellWidget(r, c, w)

    def _remove_selected_row(self) -> None:
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl.removeRow(r)
        if self.tbl.rowCount() == 0:
            self._add_row("DBM")

    # ----- project handling -----
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last_result = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        row = self.db.latest_material_quantity(pid)
        self.btn_export.setEnabled(row is not None)
        if row and row.inputs_json:
            self._prefill(row.inputs_json)

    def _prefill(self, inputs_json: str) -> None:
        try:
            d = json.loads(inputs_json)
        except (TypeError, json.JSONDecodeError):
            return
        layers = d.get("layers") or []
        if not layers:
            return
        self.tbl.setRowCount(0)
        for L in layers:
            self._add_row(L.get("layer_type", "DBM"))
            r = self.tbl.rowCount() - 1
            self.tbl.cellWidget(r, 1).setValue(float(L.get("length_m", 1000)))
            self.tbl.cellWidget(r, 2).setValue(float(L.get("width_m", 3.5)))
            self.tbl.cellWidget(r, 3).setValue(float(L.get("thickness_mm", 40)))
            self.tbl.cellWidget(r, 4).setValue(float(L.get("density_t_m3") or 0))
            self.tbl.cellWidget(r, 5).setValue(float(L.get("binder_pct") or 0))
            self.tbl.cellWidget(r, 6).setValue(float(L.get("spray_rate_kgm2") or 0))
            self.tbl.cellWidget(r, 7).setValue(float(L.get("waste_pct", 2.0)))

    # ----- compute / save -----
    def _collect(self) -> MaterialQuantityInput:
        layers: list[LayerInput] = []
        for r in range(self.tbl.rowCount()):
            combo: QComboBox = self.tbl.cellWidget(r, 0)
            length = self.tbl.cellWidget(r, 1).value()
            width = self.tbl.cellWidget(r, 2).value()
            thick = self.tbl.cellWidget(r, 3).value()
            dens = self.tbl.cellWidget(r, 4).value()
            pb = self.tbl.cellWidget(r, 5).value()
            spray = self.tbl.cellWidget(r, 6).value()
            waste = self.tbl.cellWidget(r, 7).value()
            layers.append(LayerInput(
                layer_type=combo.currentText(),
                length_m=length, width_m=width, thickness_mm=thick,
                density_t_m3=(dens if dens > 0 else None),
                binder_pct=(pb if pb > 0 else None),
                spray_rate_kgm2=(spray if spray > 0 else None),
                waste_pct=waste,
            ))
        return MaterialQuantityInput(
            project_id=self._project_id, layers=tuple(layers))

    def _on_compute(self) -> None:
        try:
            inp = self._collect()
            if not inp.layers:
                QMessageBox.warning(self, "No layers",
                    "Add at least one layer row.")
                return
            r = compute_material_quantity(inp)
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last_result = r
        self._render(r)
        self.btn_save.setEnabled(self._project_id is not None)

    def _render(self, r: MaterialQuantityResult) -> None:
        self.res_card.setVisible(True)
        self.lbl_totals.setText(
            f"Σ Layer = {r.total_layer_tonnage_t:.2f} t   ·   "
            f"Σ Binder = {r.total_binder_tonnage_t:.2f} t   ·   "
            f"Area = {r.total_area_m2:.0f} m²"
        )
        self.res_tbl.setRowCount(len(r.layers))
        for i, lr in enumerate(r.layers):
            ref = lr.code_refs[0].code_id if lr.code_refs else "—"
            cells = [
                lr.inputs.layer_type,
                f"{lr.area_m2:.1f}",
                f"{lr.layer_tonnage_t:.2f}",
                f"{lr.binder_tonnage_t:.2f}",
                ref,
            ]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c > 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.res_tbl.setItem(i, c, it)
        self.lbl_notes.setText(r.notes)

    def _on_save(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        try:
            self.db.save_material_quantity(
                project_id=self._project_id, result=self._last_result)
            self.db.set_module_status(
                self._project_id, "material_qty", "complete")
            self.btn_export.setEnabled(True)
            QMessageBox.information(self, "Saved",
                "Material-quantity BOQ saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)

    def last_result(self) -> MaterialQuantityResult | None:
        return self._last_result
