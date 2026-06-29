"""Material Quantity Calculator — Phase 7 & 4.

One-page form: a layer table where each row is a LayerInput. Compute
button aggregates tonnages; Save persists to MaterialQuantityDesign;
Export Word/Excel emits the BOQ section.
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
    QFormLayout,
    QTabWidget,
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
from app.engineering.boq_engine import get_material_key, format_indian_currency, DEFAULT_RATES
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


def get_final_pavement_layers(db, project_id: int) -> list[dict]:
    p = db.get_project(project_id)
    if not p:
        return []
    
    selected_opt = p.selected_design_option
    sd = db.latest_structural_design(project_id)
    stab = db.latest_stabilized_design(project_id)
    
    comp = []
    if selected_opt:
        if "Option B" in selected_opt:
            if stab:
                try:
                    res_data = json.loads(stab.results_json) if isinstance(stab.results_json, str) else stab.results_json
                    comp = res_data.get("stabilized_composition", [])
                except Exception:
                    pass
        elif "Option C" in selected_opt:
            if stab:
                try:
                    res_data = json.loads(stab.results_json) if isinstance(stab.results_json, str) else stab.results_json
                    comp = res_data.get("stabilized_composition", [])
                except Exception:
                    pass
            if not comp and sd:
                try:
                    comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
                except Exception:
                    pass
        elif "Option D" in selected_opt:
            try:
                from app.engineering.boq_engine import generate_boq
                boq_data = generate_boq(project_id, db)
                best_opt_key = boq_data.get("options", {}).get("Option D", {}).get("selected_reference")
                if best_opt_key == "Option B" and stab:
                    res_data = json.loads(stab.results_json) if isinstance(stab.results_json, str) else stab.results_json
                    comp = res_data.get("stabilized_composition", [])
                elif sd:
                    comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
            except Exception:
                pass
        else: # Option A
            if sd:
                try:
                    comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
                except Exception:
                    pass
    else:
        if sd:
            try:
                comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
                if not comp and stab:
                    res_data = json.loads(stab.results_json) if isinstance(stab.results_json, str) else stab.results_json
                    comp = res_data.get("stabilized_composition", [])
            except Exception:
                pass
        elif stab:
            try:
                res_data = json.loads(stab.results_json) if isinstance(stab.results_json, str) else stab.results_json
                comp = res_data.get("stabilized_composition", [])
            except Exception:
                pass
                
    return comp


class MaterialQuantityPanel(QWidget):
    """Independent BOQ panel."""

    saved = Signal(int)
    export_requested = Signal(int)
    export_excel_requested = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last_result: MaterialQuantityResult | None = None
        self._build()
        self._load_rates()
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
        
        self.btn_export_excel = styled_button("Export Excel", "secondary")
        self.btn_export_excel.clicked.connect(self._on_export_excel)
        self.btn_export_excel.setEnabled(False)

        self.btn_toggle_rates = styled_button("Manage Rates", "secondary")
        self.btn_toggle_rates.clicked.connect(self._toggle_rates_visible)
        
        self.btn_refresh = styled_button("Refresh Structural Design", "secondary")
        self.btn_refresh.clicked.connect(self._on_refresh_source)

        for b in (self.btn_toggle_rates, self.btn_refresh, self.btn_export_excel, self.btn_export,
                  self.btn_save, self.btn_compute, self.btn_remove, self.btn_add):
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

        # Project Geometry Card
        self.geom_card = Card()
        gl = QHBoxLayout(self.geom_card)
        gl.setContentsMargins(16, 12, 16, 12); gl.setSpacing(12)
        gl.addWidget(QLabel("<b>Project Geometry:</b>"))
        
        gl.addWidget(QLabel("Road Length (m):"))
        self.sp_road_length = _spin(1000.0, 0, 1e6, 100, 1)
        gl.addWidget(self.sp_road_length)
        
        gl.addWidget(QLabel("Carriageway Width (m):"))
        self.sp_carriageway_width = _spin(7.0, 0, 100, 0.5, 2)
        gl.addWidget(self.sp_carriageway_width)
        
        gl.addWidget(QLabel("Shoulder Width (m):"))
        self.sp_shoulder_width = _spin(1.5, 0, 100, 0.5, 2)
        gl.addWidget(self.sp_shoulder_width)
        
        self.btn_apply_geom = styled_button("Apply to Layers", "secondary")
        self.btn_apply_geom.clicked.connect(self._apply_geometry_to_layers)
        gl.addWidget(self.btn_apply_geom)
        
        bl.addWidget(self.geom_card)

        # Rate Editor Card (hidden by default)
        self.rate_card = Card()
        rl_card = QVBoxLayout(self.rate_card)
        rl_card.setContentsMargins(16, 12, 16, 12); rl_card.setSpacing(8)
        
        hdr_lbl = QLabel("<b>Rate Manager (Sample/Default Rates)</b>")
        rl_card.addWidget(hdr_lbl)
        
        warn_lbl = QLabel(
            "⚠ <b>WARNING:</b> These are sample/default rates. "
            "You MUST update project-specific market/SOR rates before final submission."
        )
        warn_lbl.setStyleSheet("color: #b7791f; font-weight: bold;")
        warn_lbl.setWordWrap(True)
        rl_card.addWidget(warn_lbl)
        
        self.rate_form = QFormLayout()
        self.rate_inputs = {}
        materials = ["BC", "DBM", "WMM", "GSB", "Bitumen", "Cement", "Aggregate"]
        for mat in materials:
            row_lay = QHBoxLayout()
            sb = _spin(0.0, 0, 1e6, 100, 2)
            sb.setMinimumWidth(120)
            
            uc = QComboBox()
            uc.addItems(["Tonne", "Cum"])
            uc.setMinimumWidth(80)
            
            row_lay.addWidget(sb)
            row_lay.addWidget(uc)
            row_lay.addStretch(1)
            
            self.rate_inputs[mat] = (sb, uc)
            self.rate_form.addRow(f"{mat} Rate (₹):", row_lay)
            
        rl_card.addLayout(self.rate_form)
        
        btn_save_rates = styled_button("Save Rates", "secondary")
        btn_save_rates.clicked.connect(self._save_rates)
        rl_card.addWidget(btn_save_rates)
        
        self.rate_card.setVisible(False)
        bl.addWidget(self.rate_card)

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
        rl.setContentsMargins(16, 12, 16, 12); rl.setSpacing(8)
        rl.addWidget(QLabel("<b>Computed Results — Preliminary Engineering Estimate</b>"))
        
        self.res_tabs = QTabWidget()
        rl.addWidget(self.res_tabs)

        # Tab 1: Quantity & Cost Abstract
        self.tab_abstract = QWidget()
        tl1 = QVBoxLayout(self.tab_abstract)
        tl1.setContentsMargins(10, 10, 10, 10); tl1.setSpacing(10)
        
        self.lbl_totals = QLabel("Total: —")
        self.lbl_totals.setStyleSheet("font-size:11pt; font-weight:bold; color:#1d7a3a;")
        tl1.addWidget(self.lbl_totals)
        
        self.res_tbl = QTableWidget(0, 9)
        self.res_tbl.setHorizontalHeaderLabels([
            "Layer", "Thickness (mm)", "Compacted (m³)", "Loose (m³)", 
            "Quantity", "Unit", "Rate Source", "Rate (₹)", "Amount (₹)"
        ])
        self.res_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.res_tbl.verticalHeader().setVisible(False)
        tl1.addWidget(self.res_tbl)
        
        self.lbl_notes = QLabel("")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        tl1.addWidget(self.lbl_notes)
        self.res_tabs.addTab(self.tab_abstract, "Quantity & Cost Abstract")

        # Tab 2: Material Consumption Splits
        self.tab_splits = QWidget()
        tl2 = QVBoxLayout(self.tab_splits)
        tl2.setContentsMargins(10, 10, 10, 10); tl2.setSpacing(10)
        
        tl2.addWidget(QLabel("<b>Cumulative Material Tonnage Consumption</b>"))
        self.lbl_splits_summary = QLabel("—")
        self.lbl_splits_summary.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 4px; "
            "padding: 12px; color: #1e3a8a; font-size: 10.5pt; line-height: 1.5;"
        )
        tl2.addWidget(self.lbl_splits_summary)
        tl2.addStretch(1)
        self.res_tabs.addTab(self.tab_splits, "Material Consumption Splits")

        # Tab 3: BOQ Validation & Traceability
        self.tab_val_trace = QWidget()
        tl3 = QVBoxLayout(self.tab_val_trace)
        tl3.setContentsMargins(10, 10, 10, 10); tl3.setSpacing(10)
        
        tl3.addWidget(QLabel("<b>BOQ Validation Checks</b>"))
        self.lbl_validation_status = QLabel("—")
        self.lbl_validation_status.setWordWrap(True)
        self.lbl_validation_status.setStyleSheet(
            "background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px; "
            "padding: 10px; color: #374151; font-size: 9.5pt;"
        )
        tl3.addWidget(self.lbl_validation_status)
        
        tl3.addWidget(QLabel("<b>Pavement Quantity Traceability Log</b>"))
        self.lbl_traceability = QLabel("—")
        self.lbl_traceability.setWordWrap(True)
        self.lbl_traceability.setStyleSheet(
            "font-family: 'Courier New', Courier, monospace; background-color: #fafaf9; "
            "border: 1px solid #e7e5e4; border-radius: 4px; padding: 10px; font-size: 9.5pt; color: #44403c;"
        )
        tl3.addWidget(self.lbl_traceability)
        self.res_tabs.addTab(self.tab_val_trace, "Validation & Traceability")

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

    # ----- rate editor helpers -----
    def _toggle_rates_visible(self) -> None:
        self.rate_card.setVisible(not self.rate_card.isVisible())

    def _load_rates(self) -> None:
        try:
            rates = self.db.list_material_rates()
            for r in rates:
                if r.material in self.rate_inputs:
                    sb, uc = self.rate_inputs[r.material]
                    sb.setValue(r.rate)
                    uc.setCurrentText(r.unit)
        except Exception as e:
            print("Error loading rates:", e)

    def _save_rates(self) -> None:
        try:
            for mat, (sb, uc) in self.rate_inputs.items():
                self.db.save_material_rate(mat, uc.currentText(), sb.value())
            QMessageBox.information(self, "Rates Saved", "Material rates saved successfully.")
            if self._last_result:
                self._render(self._last_result)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save rates: {str(e)}")

    def _apply_geometry_to_layers(self) -> None:
        L = self.sp_road_length.value()
        W = self.sp_carriageway_width.value()
        S = self.sp_shoulder_width.value()
        for r in range(self.tbl.rowCount()):
            combo: QComboBox = self.tbl.cellWidget(r, 0)
            layer_type = combo.currentText()
            material_key = get_material_key(layer_type)
            
            self.tbl.cellWidget(r, 1).setValue(L)
            if material_key in ("WMM", "GSB"):
                self.tbl.cellWidget(r, 2).setValue(W + 2 * S)
            else:
                self.tbl.cellWidget(r, 2).setValue(W)

    # ----- project handling -----
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last_result = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            self.btn_export_excel.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        
        # Check if structural design exists (Option A, B, C, or D)
        comp = get_final_pavement_layers(self.db, pid)
        row = self.db.latest_material_quantity(pid)
        self.btn_export.setEnabled(row is not None)
        self.btn_export_excel.setEnabled(row is not None)
        
        if comp:
            saved_dict = {}
            if row and row.inputs_json:
                try:
                    saved_dict = json.loads(row.inputs_json) if isinstance(row.inputs_json, str) else row.inputs_json
                except Exception:
                    pass
            
            # Geometry defaults
            road_length = float(saved_dict.get("road_length_m", 1000.0))
            carriageway_width = float(saved_dict.get("carriageway_width_m", 7.0))
            shoulder_width = float(saved_dict.get("shoulder_width_m", 1.5))
            
            self.sp_road_length.setValue(road_length)
            self.sp_carriageway_width.setValue(carriageway_width)
            self.sp_shoulder_width.setValue(shoulder_width)
            
            # Map saved layers
            saved_layers = {L.get("layer_type"): L for L in saved_dict.get("layers", [])}
            
            self.tbl.setRowCount(0)
            
            def map_layer_name(cname: str) -> str:
                cname_upper = cname.upper()
                if "BC" in cname_upper or "CONCRETE" in cname_upper or "WEARING" in cname_upper:
                    return "BC"
                if "DBM" in cname_upper or "BINDER" in cname_upper or "BM" in cname_upper or "BITUMINOUS" in cname_upper:
                    return "DBM"
                if "WMM" in cname_upper or "WET MIX" in cname_upper:
                    return "WMM"
                if "GSB" in cname_upper or "SUB-BASE" in cname_upper or "SUBBASE" in cname_upper or "GRANULAR" in cname_upper:
                    return "GSB"
                if "CTB" in cname_upper:
                    return "CTB"
                if "CTS" in cname_upper:
                    return "CTS"
                return "DBM"
            
            # Add structural layers in order
            for ly in comp:
                ly_name = ly.get("name", "")
                ly_thick = float(ly.get("thickness_mm", 40.0))
                mapped_type = map_layer_name(ly_name)
                
                saved_ly = saved_layers.get(mapped_type, {})
                self._add_row(mapped_type)
                r = self.tbl.rowCount() - 1
                
                # Thickness is strictly from structural design suggestion
                self.tbl.cellWidget(r, 3).setValue(ly_thick)
                
                L_val = float(saved_ly.get("length_m") if saved_ly.get("length_m") is not None else road_length)
                self.tbl.cellWidget(r, 1).setValue(L_val)
                
                if mapped_type in ("WMM", "GSB", "CTB", "CTS"):
                    default_W = carriageway_width + 2 * shoulder_width
                else:
                    default_W = carriageway_width
                W_val = float(saved_ly.get("width_m") if saved_ly.get("width_m") is not None else default_W)
                self.tbl.cellWidget(r, 2).setValue(W_val)
                
                self.tbl.cellWidget(r, 4).setValue(float(saved_ly.get("density_t_m3") or 0.0))
                self.tbl.cellWidget(r, 5).setValue(float(saved_ly.get("binder_pct") or 0.0))
                self.tbl.cellWidget(r, 6).setValue(float(saved_ly.get("spray_rate_kgm2") or 0.0))
                self.tbl.cellWidget(r, 7).setValue(float(saved_ly.get("waste_pct") if saved_ly.get("waste_pct") is not None else 2.0))
                
            # Add sprayed coats if they exist in saved or default
            for coat in ("Prime Coat", "Tack Coat"):
                saved_ly = saved_layers.get(coat)
                if saved_ly or not saved_layers:
                    self._add_row(coat)
                    r = self.tbl.rowCount() - 1
                    saved_ly = saved_ly or {}
                    
                    self.tbl.cellWidget(r, 1).setValue(float(saved_ly.get("length_m") if saved_ly.get("length_m") is not None else road_length))
                    self.tbl.cellWidget(r, 2).setValue(float(saved_ly.get("width_m") if saved_ly.get("width_m") is not None else carriageway_width))
                    self.tbl.cellWidget(r, 3).setValue(float(saved_ly.get("thickness_mm") if saved_ly.get("thickness_mm") is not None else 0.0))
                    self.tbl.cellWidget(r, 4).setValue(float(saved_ly.get("density_t_m3") or 0.0))
                    self.tbl.cellWidget(r, 5).setValue(float(saved_ly.get("binder_pct") or 0.0))
                    self.tbl.cellWidget(r, 6).setValue(float(saved_ly.get("spray_rate_kgm2") or 0.0))
                    self.tbl.cellWidget(r, 7).setValue(float(saved_ly.get("waste_pct") if saved_ly.get("waste_pct") is not None else 2.0))
        else:
            if row and row.inputs_json:
                self._prefill(row.inputs_json)
            else:
                self.sp_road_length.setValue(1000.0)
                self.sp_carriageway_width.setValue(7.0)
                self.sp_shoulder_width.setValue(1.5)
                self.tbl.setRowCount(0)
                self._seed_default_rows()

    def _on_refresh_source(self) -> None:
        self.refresh_from_source()

    def refresh_from_source(self) -> None:
        if self._project_id is None:
            return
            
        self.db.log_project_audit(self._project_id, "material_qty", "Refresh", "Refreshed layer thicknesses from structural design.")
        self.set_project(self._project_id, self.proj_banner.text())
        self.db.mark_module_synced(self._project_id, "material_qty", ["structural"])
        self._on_compute()
        self._on_save()
        
        # Refresh parent status badge
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "refresh_project_status_badge"):
                parent.refresh_project_status_badge()
                break
            parent = parent.parent()
            
        QMessageBox.information(self, "Refreshed", "Structural design layers refreshed and BOQ recalculated successfully.")

    def _prefill(self, inputs_json: str) -> None:
        try:
            d = json.loads(inputs_json)
        except (TypeError, json.JSONDecodeError):
            return
            
        if "road_length_m" in d:
            self.sp_road_length.setValue(float(d["road_length_m"]))
        if "carriageway_width_m" in d:
            self.sp_carriageway_width.setValue(float(d["carriageway_width_m"]))
        if "shoulder_width_m" in d:
            self.sp_shoulder_width.setValue(float(d["shoulder_width_m"]))

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
            project_id=self._project_id,
            layers=tuple(layers),
            road_length_m=self.sp_road_length.value(),
            carriageway_width_m=self.sp_carriageway_width.value(),
            shoulder_width_m=self.sp_shoulder_width.value()
        )

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
        
        # Fetch rates from DB
        db_rates = self.db.list_material_rates()
        rates = {rate.material: {"rate": rate.rate, "unit": rate.unit} for rate in db_rates}
        for k, v in DEFAULT_RATES.items():
            if k not in rates:
                rates[k] = v

        self.res_tbl.setRowCount(len(r.layers))
        total_boq_amount = 0.0
        
        total_compacted = 0.0
        total_loose = 0.0
        total_bitumen = 0.0
        total_cement = 0.0
        total_filler = 0.0
        total_aggregate = 0.0
        
        traceability_steps = []
        
        for i, lr in enumerate(r.layers):
            layer_type = lr.inputs.layer_type
            thick = lr.inputs.thickness_mm
            area = lr.area_m2
            category = lr.category
            density = lr.inputs.density_t_m3 if lr.inputs.density_t_m3 is not None else DEFAULT_DENSITY.get(layer_type, 2.20)
            
            material_key = get_material_key(layer_type)
            vol = lr.compacted_volume_m3
            loose_vol = lr.loose_volume_m3
            
            # Sum totals
            total_compacted += vol
            total_loose += loose_vol
            total_bitumen += lr.binder_tonnage_t
            total_cement += lr.cement_tonnage_t
            total_filler += lr.filler_tonnage_t
            total_aggregate += lr.aggregate_tonnage_t

            # Calculate Quantity and Rate
            rate_source = "Preliminary Estimate"
            if category == "sprayed_coat":
                qty = lr.binder_tonnage_t
                unit = "Tonne"
                r_info = rates.get("Bitumen", DEFAULT_RATES["Bitumen"])
                rate = r_info.get("rate", 0.0)
                if "Bitumen" in rates:
                    rate_source = "Project rate"
                amount = qty * rate
                vol_str, loose_vol_str, dens_str, thick_str = "—", "—", "—", "—"
            elif layer_type.upper() in ("CTB", "CTS") or material_key == "STABILIZED":
                qty = lr.layer_tonnage_t
                unit = "Tonne"
                cement_pct = 4.5 if layer_type.upper() == "CTB" else 3.0
                if lr.inputs.binder_pct is not None and lr.inputs.binder_pct > 0.0:
                    cement_pct = lr.inputs.binder_pct
                cement_t = qty * cement_pct / 100.0
                agg_t = qty - cement_t
                c_rate = rates.get("Cement", {}).get("rate", DEFAULT_RATES["Cement"]["rate"])
                agg_rate = rates.get("Aggregate", {}).get("rate", DEFAULT_RATES["Aggregate"]["rate"])
                if "Cement" in rates and "Aggregate" in rates:
                    rate_source = "Project rate"
                amount = (cement_t * c_rate) + (agg_t * agg_rate)
                rate = amount / qty if qty > 0 else agg_rate
                unit = "Tonne"
                vol_str = f"{vol:.1f}"
                loose_vol_str = f"{loose_vol:.1f}"
                dens_str = f"{density:.2f}"
                thick_str = f"{thick:.0f}"
            else:
                qty = lr.layer_tonnage_t
                r_info = rates.get(material_key, DEFAULT_RATES.get(material_key, {}))
                unit = r_info.get("unit", "Tonne")
                rate = r_info.get("rate", 0.0)
                if material_key in rates:
                    rate_source = "Project rate"
                if unit.lower() in ("cum", "m3"):
                    qty = vol
                amount = qty * rate
                vol_str = f"{vol:.1f}"
                loose_vol_str = f"{loose_vol:.1f}"
                dens_str = f"{density:.2f}"
                thick_str = f"{thick:.0f}"

            total_boq_amount += amount
            
            # Traceability step text
            waste_pct = lr.inputs.waste_pct
            if category == "sprayed_coat":
                tr = f"• {layer_type}: Bitumen Tonnage ({qty:.2f} t) = Area ({area:.1f} m²) × Spray Rate ({lr.inputs.spray_rate_kgm2 or DEFAULT_SPRAY_RATE_KGM2.get(layer_type, 0.25):.2f} kg/m² / 1000)"
            else:
                tr = f"• {layer_type}: Compacted Vol ({vol:.1f} m³) = L ({lr.inputs.length_m:.1f} m) × W ({lr.inputs.width_m:.1f} m) × Thickness ({thick:.0f} mm / 1000)\n" \
                     f"  Compacted Tonnage ({lr.layer_tonnage_t:.2f} t) = Vol ({vol:.1f} m³) × Density ({density:.2f} t/m³) × Waste ({1 + waste_pct/100:.2f})\n" \
                     f"  Loose Vol ({loose_vol:.1f} m³) = Compacted Vol × bulking factor"
            traceability_steps.append(tr)

            cells = [
                layer_type,
                thick_str,
                vol_str,
                loose_vol_str,
                f"{qty:.2f}",
                unit,
                rate_source,
                f"₹{rate:,.2f}",
                f"₹{amount:,.2f}"
            ]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c > 0:
                    it.setTextAlignment(Qt.AlignCenter if c in (1, 2, 3, 5) else Qt.AlignRight)
                self.res_tbl.setItem(i, c, it)

        # GST and Grand Total calculations
        gst = total_boq_amount * 0.18
        grand_total = total_boq_amount + gst

        self.lbl_totals.setText(
            f"Preliminary Engineering Estimate:\n"
            f"  Subtotal Amount  = ₹{total_boq_amount:,.2f}\n"
            f"  GST (18% tax)    = ₹{gst:,.2f}\n"
            f"  Grand Total Cost = ₹{grand_total:,.2f}"
        )
        self.lbl_notes.setText(
            f"Σ Compacted = {total_compacted:.1f} m³   ·   "
            f"Σ Loose = {total_loose:.1f} m³   ·   "
            f"Total Area = {r.total_area_m2:.0f} m²\n\n"
            f"{r.notes}"
        )
        
        # Populate splits on Tab 2
        splits_html = (
            f"<b>Aggregate (Stone/Granular):</b> {total_aggregate:,.2f} Tonnes<br>"
            f"<b>Bitumen (Binder):</b> {total_bitumen:,.2f} Tonnes<br>"
            f"<b>Cement Binder:</b> {total_cement:,.2f} Tonnes<br>"
            f"<b>Mineral Filler (Dust):</b> {total_filler:,.2f} Tonnes<br><br>"
            f"<i>Constituent calculations are derived from compacted dry density, mix design percentages, and waste tolerances.</i>"
        )
        self.lbl_splits_summary.setText(splits_html)

        # BOQ Validation Checks
        errors = []
        warnings = []
        
        # Missing/negative value checks
        for lr in r.layers:
            if lr.inputs.length_m <= 0 or lr.inputs.width_m <= 0:
                errors.append(f"Negative or zero geometry detected for layer '{lr.inputs.layer_type}'.")
                
        # Load structural design to verify thickness consistency
        sd = self.db.latest_structural_design(self._project_id) if self._project_id else None
        if sd:
            try:
                comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
            except Exception:
                comp = []
                
            struct_thicknesses = {}
            for s_ly in comp:
                s_name = s_ly.get("name", "").upper()
                struct_thicknesses[s_name] = float(s_ly.get("thickness_mm", 0.0))
                
            # Verify if each layer exists
            for lr in r.layers:
                layer_type = lr.inputs.layer_type
                if layer_type in ("Prime Coat", "Tack Coat"):
                    continue
                matched_s_name = None
                for s_name in struct_thicknesses:
                    if layer_type.upper() in s_name or s_name in layer_type.upper():
                        matched_s_name = s_name
                        break
                if matched_s_name:
                    s_thick = struct_thicknesses[matched_s_name]
                    if abs(lr.inputs.thickness_mm - s_thick) > 0.1:
                        warnings.append(
                            f"Thickness mismatch for '{layer_type}': "
                            f"BOQ = {lr.inputs.thickness_mm:.0f} mm, Structural Design = {s_thick:.0f} mm."
                        )
                else:
                    warnings.append(f"Layer '{layer_type}' in BOQ does not match any layer in the approved structural design.")
        else:
            errors.append("No approved structural design found to validate thicknesses.")

        val_status = "PASS" if not errors else "FAIL"
        color = "#166534" if val_status == "PASS" else "#9b1c1c"
        bg_color = "#f0fdf4" if val_status == "PASS" else "#fff5f5"
        border_color = "#bbf7d0" if val_status == "PASS" else "#fed7d7"
        
        err_msg = "<br>".join(f"❌ {e}" for e in errors) if errors else "<i>No critical quantity errors found.</i>"
        warn_msg = "<br>".join(f"⚠️ {w}" for w in warnings) if warnings else "<i>No quantity warnings found.</i>"
        
        self.lbl_validation_status.setStyleSheet(
            f"background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 4px; "
            f"padding: 10px; color: {color}; font-size: 10pt;"
        )
        self.lbl_validation_status.setText(
            f"<b>Validation Status: {val_status}</b><br><br>"
            f"<b>Critical Errors:</b><br>{err_msg}<br><br>"
            f"<b>Warnings / Mismatches:</b><br>{warn_msg}"
        )
        
        self.lbl_traceability.setText("\n\n".join(traceability_steps))

    def _on_save(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        try:
            self.db.save_material_quantity(
                project_id=self._project_id, result=self._last_result)
            self.db.set_module_status(
                self._project_id, "material_qty", "complete")
            self.btn_export.setEnabled(True)
            self.btn_export_excel.setEnabled(True)
            QMessageBox.information(self, "Saved",
                "Material-quantity BOQ saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)

    def _on_export_excel(self) -> None:
        if self._project_id is None:
            return
        self.export_excel_requested.emit(self._project_id)

    def last_result(self) -> MaterialQuantityResult | None:
        return self._last_result

