"""Traffic / ESAL / MSA panel — Phase 8.

Independent panel: CVPD/r/n/terrain/lane-config form, Compute, Save,
Export Word. Follows the same shape as material_qty_panel.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    LANE_CONFIGS,
    TERRAINS,
    TrafficInput,
    TrafficResult,
    compute_traffic_analysis,
    ldf_preset,
    vdf_preset,
)
from .common import Card, PageHeader, styled_button


ROAD_CATEGORIES = (
    "NH / SH", "Expressway", "MDR", "ODR", "Village Road",
    "Urban Arterial", "Other",
)


def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(f" {suffix}")
    return sp


class TrafficPanel(QWidget):
    """Independent traffic analysis page."""

    saved = Signal(int)
    export_requested = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last: TrafficResult | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Traffic / ESAL / MSA Analysis",
            "IRC:37-2018 cl. 4.6 — design traffic; VDF (Table 1) / LDF (cl. 4.4)"
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
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(12)

        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;")
        bl.addWidget(self.proj_banner)

        # Inputs
        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        self.road_cat = QComboBox()
        for c in ROAD_CATEGORIES:
            self.road_cat.addItem(c)
        self.terrain = QComboBox()
        for t in TERRAINS:
            self.terrain.addItem(t)
        self.lane = QComboBox()
        for L in LANE_CONFIGS:
            self.lane.addItem(L)
        self.lane.setCurrentText("Two-lane carriageway")

        self.cvpd  = _spin(2000, 0, 1_000_000, 100, 0, "CVPD")
        self.growth = _spin(7.5, 0, 30, 0.5, 2, "%")
        self.life  = QSpinBox(); self.life.setRange(1, 50); self.life.setValue(15); self.life.setSuffix(" yr")
        self.vdf   = _spin(0.0, 0, 20, 0.1, 2)
        self.vdf.setSpecialValueText(" (auto from IRC:37 Table 1)")
        self.ldf   = _spin(0.0, 0, 1, 0.05, 2)
        self.ldf.setSpecialValueText(" (auto from IRC:37 cl. 4.4)")

        form.addRow("Road Category", self.road_cat)
        form.addRow("Terrain", self.terrain)
        form.addRow("Lane Configuration", self.lane)
        form.addRow("Initial Commercial Traffic (A)", self.cvpd)
        form.addRow("Growth Rate (r)", self.growth)
        form.addRow("Design Life (n)", self.life)
        form.addRow("VDF (F) — override", self.vdf)
        form.addRow("LDF (D) — override", self.ldf)
        bl.addWidget(in_card)

        # Preset preview (read-only, updates live)
        self.preset_lbl = QLabel("")
        self.preset_lbl.setStyleSheet("color:#6a7180; font-size:9pt;")
        bl.addWidget(self.preset_lbl)
        for w in (self.terrain, self.lane):
            w.currentTextChanged.connect(self._refresh_preset_hint)
        self.cvpd.valueChanged.connect(self._refresh_preset_hint)
        self._refresh_preset_hint()

        # Results
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>Computed Traffic</b>"))
        self.lbl_msa = QLabel("Design Traffic: —")
        self.lbl_msa.setStyleSheet("font-size:13pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_msa)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet("color:#6a7180; font-size:10pt;")
        rl.addWidget(self.lbl_meta)
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

    def _refresh_preset_hint(self) -> None:
        try:
            vp = vdf_preset(self.terrain.currentText(), self.cvpd.value())
            lp = ldf_preset(self.lane.currentText())
            self.preset_lbl.setText(
                f"IRC:37 presets — VDF (Table 1) ≈ {vp:g} · "
                f"LDF (cl. 4.4) ≈ {lp:g}. Leave overrides at 0 to use these."
            )
        except Exception:
            pass

    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        row = self.db.latest_traffic_analysis(pid)
        self.btn_export.setEnabled(row is not None)
        if row and row.inputs_json:
            try:
                d = json.loads(row.inputs_json)
                self.road_cat.setCurrentText(d.get("road_category", "NH / SH"))
                self.terrain.setCurrentText(d.get("terrain", "Plain"))
                self.lane.setCurrentText(d.get("lane_config", "Two-lane carriageway"))
                self.cvpd.setValue(float(d.get("initial_cvpd", 2000)))
                self.growth.setValue(float(d.get("growth_rate_pct", 7.5)))
                self.life.setValue(int(d.get("design_life_years", 15)))
                self.vdf.setValue(float(d.get("vdf") or 0))
                self.ldf.setValue(float(d.get("ldf") or 0))
            except Exception:
                pass

    def _collect(self) -> TrafficInput:
        return TrafficInput(
            initial_cvpd=self.cvpd.value(),
            growth_rate_pct=self.growth.value(),
            design_life_years=self.life.value(),
            terrain=self.terrain.currentText(),
            lane_config=self.lane.currentText(),
            vdf=(self.vdf.value() if self.vdf.value() > 0 else None),
            ldf=(self.ldf.value() if self.ldf.value() > 0 else None),
            road_category=self.road_cat.currentText(),
        )

    def _on_compute(self) -> None:
        try:
            r = compute_traffic_analysis(self._collect())
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last = r
        self.res_card.setVisible(True)
        self.lbl_msa.setText(
            f"Design Traffic = {r.design_msa:.2f} MSA  ·  "
            f"AASHTO ESAL = {r.aashto_esal:,.0f}"
        )
        self.lbl_meta.setText(
            f"Category: <b>{r.traffic_category}</b>  ·  "
            f"GF = {r.growth_factor:.3f}  ·  "
            f"VDF used = {r.vdf_used:g}  ·  LDF used = {r.ldf_used:g}"
        )
        self.lbl_notes.setText(r.notes)
        self.btn_save.setEnabled(self._project_id is not None)

    def _on_save(self) -> None:
        if self._project_id is None or self._last is None:
            return
        try:
            self.db.save_traffic_analysis(
                project_id=self._project_id, result=self._last)
            self.db.set_module_status(self._project_id, "traffic", "complete")
            self.btn_export.setEnabled(True)
            QMessageBox.information(self, "Saved",
                "Traffic analysis saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)

    def last_result(self) -> TrafficResult | None:
        return self._last
