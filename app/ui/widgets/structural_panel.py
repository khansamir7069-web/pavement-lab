"""Flexible Pavement Structural Design panel — Phase 4 skeleton.

Independent module: needs a project but no mix-design data.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    StructuralInput,
    StructuralResult,
    compute_structural_design,
)
from .common import Card, PageHeader, styled_button


ROAD_CATEGORIES = (
    "NH / SH",
    "Expressway",
    "MDR",
    "ODR",
    "Village Road",
    "Urban Arterial",
    "Other",
)


def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(f" {suffix}")
    return sp


class StructuralPanel(QWidget):
    """Standalone structural design UI."""

    saved = Signal(int)        # emits project_id after a successful save
    export_requested = Signal(int)   # emits project_id when user clicks Export Word

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last_result: StructuralResult | None = None
        self._build()

    # ----- build -----
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Flexible Pavement Structural Design",
            "IRC:37 — traffic, subgrade & catalogue layer suggestion"
        )
        self.btn_compute = styled_button("Compute")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        self.btn_export = styled_button("Export Word", "secondary")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        self.header.add_action(self.btn_export)
        self.header.add_action(self.btn_save)
        self.header.add_action(self.btn_compute)
        lay.addWidget(self.header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(14)

        # Project banner
        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;")
        bl.addWidget(self.proj_banner)

        # ----- Inputs card -----
        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        self.road_cat = QComboBox()
        for c in ROAD_CATEGORIES:
            self.road_cat.addItem(c)
        self.design_life = QSpinBox(); self.design_life.setRange(1, 50); self.design_life.setValue(15); self.design_life.setSuffix(" yr")
        self.cvpd       = _spin(2000, 0, 1_000_000, 100, 0, "CVPD")
        self.growth     = _spin(7.5, 0, 30, 0.5, 2, "%")
        self.vdf        = _spin(2.5, 0, 20, 0.1, 2)
        self.ldf        = _spin(0.75, 0, 1, 0.05, 2)
        self.cbr        = _spin(5.0, 0.5, 50, 0.5, 1, "%")
        self.mr_mpa     = _spin(0.0, 0, 1000, 5, 1, "MPa")
        self.mr_mpa.setSpecialValueText(" (auto from CBR)")

        form.addRow("Road Category", self.road_cat)
        form.addRow("Design Life", self.design_life)
        form.addRow("Initial Commercial Traffic", self.cvpd)
        form.addRow("Traffic Growth Rate", self.growth)
        form.addRow("Vehicle Damage Factor (VDF)", self.vdf)
        form.addRow("Lane Distribution Factor (LDF)", self.ldf)
        form.addRow("Subgrade CBR (4-day soaked)", self.cbr)
        form.addRow("Resilient Modulus (optional)", self.mr_mpa)
        bl.addWidget(in_card)

        # ----- Results card -----
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(8)
        rl.addWidget(QLabel("<b>Computed Results</b>"))
        self.lbl_msa = QLabel("Design Traffic: —")
        self.lbl_msa.setStyleSheet("font-size:13pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_msa)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet("color:#6a7180; font-size:10pt;")
        rl.addWidget(self.lbl_meta)

        self.layer_table = QTableWidget(0, 4)
        self.layer_table.setHorizontalHeaderLabels(
            ["Layer", "Material", "Thickness (mm)", "Modulus (MPa)"])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layer_table.verticalHeader().setVisible(False)
        rl.addWidget(self.layer_table)

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("font-weight:bold; color:#1f3a68;")
        rl.addWidget(self.lbl_total)
        self.lbl_checks = QLabel("")
        self.lbl_checks.setWordWrap(True)
        self.lbl_checks.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        rl.addWidget(self.lbl_checks)
        self.res_card.setVisible(False)
        bl.addWidget(self.res_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

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
        # Pre-fill from latest saved structural design if any
        sd = self.db.latest_structural_design(pid)
        self.btn_export.setEnabled(sd is not None)
        if sd and sd.inputs_json:
            try:
                import json
                d = json.loads(sd.inputs_json)
                self.road_cat.setCurrentText(d.get("road_category", "NH / SH"))
                self.design_life.setValue(int(d.get("design_life_years", 15)))
                self.cvpd.setValue(float(d.get("initial_cvpd", 2000)))
                self.growth.setValue(float(d.get("growth_rate_pct", 7.5)))
                self.vdf.setValue(float(d.get("vdf", 2.5)))
                self.ldf.setValue(float(d.get("ldf", 0.75)))
                self.cbr.setValue(float(d.get("subgrade_cbr_pct", 5.0)))
                self.mr_mpa.setValue(float(d.get("resilient_modulus_mpa") or 0.0))
            except Exception:
                pass

    def _collect(self) -> StructuralInput:
        mr = self.mr_mpa.value()
        return StructuralInput(
            road_category=self.road_cat.currentText(),
            design_life_years=self.design_life.value(),
            initial_cvpd=self.cvpd.value(),
            growth_rate_pct=self.growth.value(),
            vdf=self.vdf.value(),
            ldf=self.ldf.value(),
            subgrade_cbr_pct=self.cbr.value(),
            resilient_modulus_mpa=(mr if mr > 0 else None),
        )

    # ----- compute / save -----
    def _on_compute(self) -> None:
        try:
            inp = self._collect()
            result = compute_structural_design(inp)
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last_result = result
        self._render(result)
        self.btn_save.setEnabled(self._project_id is not None)

    def _render(self, r: StructuralResult) -> None:
        self.res_card.setVisible(True)
        self.lbl_msa.setText(f"Design Traffic = {r.design_msa:.2f} MSA")
        self.lbl_meta.setText(
            f"Growth factor = {r.growth_factor:.2f}  ·  "
            f"Subgrade Mr = {r.subgrade_mr_mpa:.1f} MPa"
        )
        self.layer_table.setRowCount(len(r.composition))
        for i, ly in enumerate(r.composition):
            cells = [
                ly.name, ly.material,
                f"{ly.thickness_mm:.0f}",
                f"{ly.modulus_mpa:.0f}" if ly.modulus_mpa else "—",
            ]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                self.layer_table.setItem(i, c, it)
        self.lbl_total.setText(
            f"Total pavement thickness: {r.total_pavement_thickness_mm:.0f} mm"
        )
        self.lbl_checks.setText(
            f"Fatigue check: {r.fatigue_check}<br>"
            f"Rutting check: {r.rutting_check}<br>"
            f"<i>{r.notes}</i>"
        )

    def _on_save(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        try:
            self.db.save_structural_design(
                project_id=self._project_id, result=self._last_result
            )
            self.db.set_module_status(self._project_id, "structural", "complete")
            self.btn_export.setEnabled(True)
            QMessageBox.information(self, "Saved",
                "Structural design saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)

    def last_result(self) -> StructuralResult | None:
        return self._last_result
