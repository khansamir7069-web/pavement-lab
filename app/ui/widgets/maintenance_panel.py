"""Maintenance / Rehabilitation panel — Phase 5 skeleton.

Three sub-tabs:
  * Overlay (BBD / IRC:81)
  * Cold Mix
  * Micro Surfacing

Each sub-tab follows the same pattern:
  - Inputs card
  - Compute button → result card
  - Save button → persists to MaintenanceDesign with the appropriate
    ``sub_module`` key and marks the project module status complete.

Independent module: needs a project but no mix-design data.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    ColdMixInput,
    ColdMixResult,
    MicroSurfacingInput,
    MicroSurfacingResult,
    OverlayInput,
    OverlayResult,
    compute_cold_mix,
    compute_micro_surfacing,
    compute_overlay,
)
from .common import Card, PageHeader, styled_button


SUBGRADE_TYPES = ("granular", "clayey", "intermediate")
ROAD_CATEGORIES = ("NH / SH", "Expressway", "MDR", "ODR", "Village Road",
                   "Urban Arterial", "Other")
MICRO_TYPES = ("Type II", "Type III")
COLD_MIX_TYPES = ("Dense-Graded", "Open-Graded")    # IRC:SP:100-2014 default


def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(f" {suffix}")
    return sp


# ---------------------------------------------------------------------------
# Overlay sub-tab
# ---------------------------------------------------------------------------

class OverlayTab(QWidget):
    """BBD overlay design (IRC:81)."""

    computed = Signal(object)            # emits OverlayResult after compute
    save_requested = Signal(object)      # emits OverlayResult when Save clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: OverlayResult | None = None
        self._build()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(10)

        # Inputs
        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        self.readings = QLineEdit("0.90, 1.10, 1.00, 1.20, 0.95")
        self.readings.setPlaceholderText("Comma-separated deflections in mm "
                                         "(e.g. 0.90, 1.10, 1.00)")
        self.pav_temp = _spin(30.0, -10, 70, 0.5, 1, "°C")
        self.bc_thick = _spin(100.0, 0, 500, 5, 0, "mm")
        self.season   = _spin(1.0, 1.0, 1.5, 0.05, 2)
        self.subgrade = QComboBox()
        for s in SUBGRADE_TYPES:
            self.subgrade.addItem(s)
        self.msa      = _spin(10.0, 0, 1000, 1, 2, "MSA")
        self.road_cat = QComboBox()
        for c in ROAD_CATEGORIES:
            self.road_cat.addItem(c)

        form.addRow("Rebound deflections (mm)", self.readings)
        form.addRow("Pavement temperature", self.pav_temp)
        form.addRow("Existing bituminous-layer thickness", self.bc_thick)
        form.addRow("Season correction factor (≥ 1.0)", self.season)
        form.addRow("Subgrade type", self.subgrade)
        form.addRow("Design traffic", self.msa)
        form.addRow("Road category", self.road_cat)
        v.addWidget(in_card)

        # Action buttons
        actions = QHBoxLayout()
        self.btn_compute = styled_button("Compute")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        actions.addStretch(1)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_compute)
        v.addLayout(actions)

        # Results
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>BBD Overlay Result</b>"))
        self.lbl_h = QLabel("Overlay thickness: —")
        self.lbl_h.setStyleSheet("font-size:13pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_h)
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
        v.addWidget(self.res_card)
        v.addStretch(1)

    # ----- public: pre-fill from saved row -----
    def prefill_from_json(self, inputs_json: str) -> None:
        try:
            d = json.loads(inputs_json)
        except (TypeError, json.JSONDecodeError):
            return
        defl = d.get("deflections_mm") or []
        if defl:
            self.readings.setText(", ".join(f"{x:g}" for x in defl))
        self.pav_temp.setValue(float(d.get("pavement_temp_c", 30.0)))
        self.bc_thick.setValue(float(d.get("bituminous_thickness_mm", 100.0)))
        self.season.setValue(float(d.get("season_factor", 1.0)))
        self.subgrade.setCurrentText(d.get("subgrade_type", "granular"))
        self.msa.setValue(float(d.get("design_traffic_msa", 10.0)))
        self.road_cat.setCurrentText(d.get("road_category", "NH / SH"))

    # ----- internals -----
    def _parse_readings(self) -> tuple[float, ...]:
        out: list[float] = []
        for tok in self.readings.text().replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                out.append(float(tok))
            except ValueError:
                raise ValueError(f"'{tok}' is not a valid deflection value.")
        return tuple(out)

    def _collect(self) -> OverlayInput:
        return OverlayInput(
            deflections_mm=self._parse_readings(),
            pavement_temp_c=self.pav_temp.value(),
            bituminous_thickness_mm=self.bc_thick.value(),
            season_factor=self.season.value(),
            subgrade_type=self.subgrade.currentText(),
            design_traffic_msa=self.msa.value(),
            road_category=self.road_cat.currentText(),
        )

    def _on_compute(self) -> None:
        try:
            inp = self._collect()
            if not inp.deflections_mm:
                QMessageBox.warning(self, "No readings",
                    "Enter at least one deflection reading (in mm).")
                return
            r = compute_overlay(inp)
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last = r
        self.res_card.setVisible(True)
        if r.overlay_required:
            self.lbl_h.setText(f"Overlay thickness = {r.overlay_thickness_mm:.0f} mm")
            self.lbl_h.setStyleSheet("font-size:13pt; font-weight:bold; color:#1d7a3a;")
        else:
            self.lbl_h.setText("No overlay required (Dc ≤ D_allow).")
            self.lbl_h.setStyleSheet("font-size:13pt; font-weight:bold; color:#a06d00;")
        self.lbl_meta.setText(
            f"n = {r.n_readings}  ·  mean = {r.mean_deflection_mm:.3f} mm  ·  "
            f"SD = {r.stdev_deflection_mm:.3f} mm<br>"
            f"Dc = {r.characteristic_deflection_mm:.3f} mm  ·  "
            f"D<sub>allow</sub> ({r.inputs.design_traffic_msa:g} MSA) = "
            f"{r.allowable_deflection_mm:.3f} mm"
        )
        self.lbl_notes.setText(r.notes)
        self.btn_save.setEnabled(True)
        self.computed.emit(r)

    def _on_save(self) -> None:
        if self._last is None:
            return
        self.save_requested.emit(self._last)

    def last_result(self) -> OverlayResult | None:
        return self._last


# ---------------------------------------------------------------------------
# Cold Mix sub-tab
# ---------------------------------------------------------------------------

class ColdMixTab(QWidget):
    computed = Signal(object)
    save_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: ColdMixResult | None = None
        self._build()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(10)

        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        self.mix_type = QComboBox()
        for c in COLD_MIX_TYPES:
            self.mix_type.addItem(c)
        self.agg     = _spin(100.0, 1, 10000, 10, 1, "kg")
        self.em_pct  = _spin(8.0, 0, 30, 0.5, 2, "%")
        self.res_pct = _spin(60.0, 0, 100, 1, 1, "%")
        self.water   = _spin(4.0, 0, 30, 0.5, 2, "%")
        self.filler  = _spin(2.0, 0, 20, 0.5, 2, "%")

        form.addRow("Cold mix type", self.mix_type)
        form.addRow("Aggregate mass (basis)", self.agg)
        form.addRow("Emulsion % (of aggregate)", self.em_pct)
        form.addRow("Emulsion residue %", self.res_pct)
        form.addRow("Added water %", self.water)
        form.addRow("Mineral filler %", self.filler)
        v.addWidget(in_card)

        actions = QHBoxLayout()
        self.btn_compute = styled_button("Compute")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        actions.addStretch(1)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_compute)
        v.addLayout(actions)

        # Result
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>Cold Mix Proportions</b>"))
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(
            "font-size:12pt; font-weight:bold; color:#1f3a68;"
        )
        rl.addWidget(self.lbl_summary)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(
            ["Component", "Mass (kg)", "% of aggregate"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        rl.addWidget(self.tbl)
        self.lbl_check = QLabel("")
        self.lbl_check.setWordWrap(True)
        rl.addWidget(self.lbl_check)
        self.lbl_notes = QLabel("")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        rl.addWidget(self.lbl_notes)
        self.res_card.setVisible(False)
        v.addWidget(self.res_card)
        v.addStretch(1)

    def prefill_from_json(self, inputs_json: str) -> None:
        try:
            d = json.loads(inputs_json)
        except (TypeError, json.JSONDecodeError):
            return
        self.mix_type.setCurrentText(d.get("mix_type", "Open-Graded"))
        self.agg.setValue(float(d.get("aggregate_mass_kg", 100.0)))
        self.em_pct.setValue(float(d.get("emulsion_pct", 8.0)))
        self.res_pct.setValue(float(d.get("emulsion_residue_pct", 60.0)))
        self.water.setValue(float(d.get("water_addition_pct", 4.0)))
        self.filler.setValue(float(d.get("filler_pct", 2.0)))

    def _collect(self) -> ColdMixInput:
        return ColdMixInput(
            aggregate_mass_kg=self.agg.value(),
            emulsion_pct=self.em_pct.value(),
            emulsion_residue_pct=self.res_pct.value(),
            water_addition_pct=self.water.value(),
            filler_pct=self.filler.value(),
            mix_type=self.mix_type.currentText(),
        )

    def _on_compute(self) -> None:
        try:
            r = compute_cold_mix(self._collect())
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last = r
        self.res_card.setVisible(True)
        self.lbl_summary.setText(
            f"Residual binder = {r.residual_binder_pct:.2f} %  ·  "
            f"Total mix mass = {r.total_mix_mass_kg:.2f} kg"
        )
        self.tbl.setRowCount(len(r.components))
        for i, c in enumerate(r.components):
            cells = [c.name, f"{c.mass_kg:.2f}", f"{c.pct_of_aggregate:.2f}"]
            for j, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if j > 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(i, j, it)
        if r.pass_check:
            self.lbl_check.setText(
                "<span style='color:#1d7a3a; font-weight:bold;'>"
                "✓ Within typical 2.5–6 % residual-binder window.</span>"
            )
        else:
            self.lbl_check.setText(
                "<span style='color:#a04848; font-weight:bold;'>"
                "⚠ Residual binder outside typical 2.5–6 % window — review.</span>"
            )
        self.lbl_notes.setText(r.notes)
        self.btn_save.setEnabled(True)
        self.computed.emit(r)

    def _on_save(self) -> None:
        if self._last is None:
            return
        self.save_requested.emit(self._last)

    def last_result(self) -> ColdMixResult | None:
        return self._last


# ---------------------------------------------------------------------------
# Micro Surfacing sub-tab
# ---------------------------------------------------------------------------

class MicroSurfacingTab(QWidget):
    computed = Signal(object)
    save_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: MicroSurfacingResult | None = None
        self._build()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(10)

        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        self.surf_type = QComboBox()
        for t in MICRO_TYPES:
            self.surf_type.addItem(t)
        self.agg     = _spin(100.0, 1, 10000, 10, 1, "kg")
        self.em_pct  = _spin(13.0, 0, 30, 0.5, 2, "%")     # IRC:SP:81 typical
        self.res_pct = _spin(62.0, 0, 100, 1, 1, "%")
        self.water   = _spin(8.0, 0, 30, 0.5, 2, "%")
        self.filler  = _spin(1.5, 0, 10, 0.5, 2, "%")

        form.addRow("Surfacing type (IRC:SP:81)", self.surf_type)
        form.addRow("Aggregate mass (basis)", self.agg)
        form.addRow("Polymer-modified emulsion %", self.em_pct)
        form.addRow("Emulsion residue %", self.res_pct)
        form.addRow("Additive water %", self.water)
        form.addRow("Mineral filler %", self.filler)
        v.addWidget(in_card)

        actions = QHBoxLayout()
        self.btn_compute = styled_button("Compute")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        actions.addStretch(1)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_compute)
        v.addLayout(actions)

        # Result
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>Micro-Surfacing Proportions</b>"))
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(
            "font-size:12pt; font-weight:bold; color:#1f3a68;"
        )
        rl.addWidget(self.lbl_summary)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(
            ["Component", "Mass (kg)", "% of aggregate"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        rl.addWidget(self.tbl)
        self.lbl_check = QLabel("")
        self.lbl_check.setWordWrap(True)
        rl.addWidget(self.lbl_check)
        self.lbl_notes = QLabel("")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        rl.addWidget(self.lbl_notes)
        self.res_card.setVisible(False)
        v.addWidget(self.res_card)
        v.addStretch(1)

    def prefill_from_json(self, inputs_json: str) -> None:
        try:
            d = json.loads(inputs_json)
        except (TypeError, json.JSONDecodeError):
            return
        self.surf_type.setCurrentText(d.get("surfacing_type", "Type II"))
        self.agg.setValue(float(d.get("aggregate_mass_kg", 100.0)))
        self.em_pct.setValue(float(d.get("emulsion_pct", 13.0)))
        self.res_pct.setValue(float(d.get("emulsion_residue_pct", 62.0)))
        self.water.setValue(float(d.get("additive_water_pct", 8.0)))
        self.filler.setValue(float(d.get("mineral_filler_pct", 1.5)))

    def _collect(self) -> MicroSurfacingInput:
        return MicroSurfacingInput(
            surfacing_type=self.surf_type.currentText(),
            aggregate_mass_kg=self.agg.value(),
            emulsion_pct=self.em_pct.value(),
            emulsion_residue_pct=self.res_pct.value(),
            additive_water_pct=self.water.value(),
            mineral_filler_pct=self.filler.value(),
        )

    def _on_compute(self) -> None:
        try:
            r = compute_micro_surfacing(self._collect())
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last = r
        self.res_card.setVisible(True)
        self.lbl_summary.setText(
            f"Residual binder = {r.residual_binder_pct:.2f} %  ·  "
            f"Total water demand = {r.total_water_demand_pct:.2f} %"
        )
        self.tbl.setRowCount(len(r.components))
        for i, c in enumerate(r.components):
            cells = [c.name, f"{c.mass_kg:.2f}", f"{c.pct_of_aggregate:.2f}"]
            for j, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if j > 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(i, j, it)
        if r.pass_check:
            self.lbl_check.setText(
                "<span style='color:#1d7a3a; font-weight:bold;'>"
                f"✓ Within {r.inputs.surfacing_type} envelopes.</span>"
            )
        else:
            details = "<br>".join(r.pass_reasons)
            self.lbl_check.setText(
                "<span style='color:#a04848; font-weight:bold;'>"
                f"⚠ Outside envelope:</span><br>{details}"
            )
        self.lbl_notes.setText(r.notes)
        self.btn_save.setEnabled(True)
        self.computed.emit(r)

    def _on_save(self) -> None:
        if self._last is None:
            return
        self.save_requested.emit(self._last)

    def last_result(self) -> MicroSurfacingResult | None:
        return self._last


# ---------------------------------------------------------------------------
# Composite panel
# ---------------------------------------------------------------------------

class MaintenancePanel(QWidget):
    """Top-level Maintenance / Rehabilitation page."""

    saved = Signal(int)        # emits project_id after any save
    export_requested = Signal(int)   # emits project_id when user clicks Export Word

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Maintenance / Rehabilitation",
            "BBD overlay (IRC:81) · Cold mix (IRC:SP:100) · Micro surfacing (IRC:SP:81)"
        )
        self.btn_export = styled_button("Export Word", "secondary")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        self.header.add_action(self.btn_export)
        lay.addWidget(self.header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(12)

        # Project banner
        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;")
        bl.addWidget(self.proj_banner)

        # Tabs
        self.tabs = QTabWidget()
        self.overlay_tab = OverlayTab()
        self.cold_tab    = ColdMixTab()
        self.micro_tab   = MicroSurfacingTab()
        self.tabs.addTab(self.overlay_tab, "BBD Overlay")
        self.tabs.addTab(self.cold_tab,    "Cold Mix")
        self.tabs.addTab(self.micro_tab,   "Micro Surfacing")
        bl.addWidget(self.tabs, stretch=1)

        # Save handlers
        self.overlay_tab.save_requested.connect(
            lambda r: self._save("overlay", r))
        self.cold_tab.save_requested.connect(
            lambda r: self._save("cold_mix", r))
        self.micro_tab.save_requested.connect(
            lambda r: self._save("micro_surfacing", r))

        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    # ----- project handling -----
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        # Pre-fill each sub-tab from its latest saved row (if any)
        any_saved = False
        for sub, tab in (
            ("overlay", self.overlay_tab),
            ("cold_mix", self.cold_tab),
            ("micro_surfacing", self.micro_tab),
        ):
            row = self.db.latest_maintenance_design(pid, sub)
            if row:
                any_saved = True
                if row.inputs_json:
                    tab.prefill_from_json(row.inputs_json)
        self.btn_export.setEnabled(any_saved)

    # ----- save handler -----
    def _save(self, sub_module: str, result) -> None:
        if self._project_id is None:
            QMessageBox.warning(self, "No project",
                "Please open or create a project first.")
            return
        try:
            self.db.save_maintenance_design(
                project_id=self._project_id,
                sub_module=sub_module,
                result=result,
            )
            self.db.set_module_status(self._project_id, "maintenance", "complete")
            self.btn_export.setEnabled(True)
            QMessageBox.information(self, "Saved",
                f"Maintenance ({sub_module}) saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)
