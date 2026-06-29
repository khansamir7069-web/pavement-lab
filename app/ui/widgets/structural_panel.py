"""Flexible Pavement Structural Design panel — Phase 4 skeleton.

Independent module: needs a project but no mix-design data.
"""
from __future__ import annotations

from datetime import datetime, timezone

import dataclasses

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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QTabWidget,
)

from app.core import (
    MECHANISTIC_WORKFLOW_NOT_RUN,
    StructuralInput,
    StructuralResult,
    compute_structural_design,
    run_structural_iitpave_mechanistic_workflow,
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


def _fmt_mech_value(value: float | None, suffix: str = "") -> str:
    return "not available" if value is None else f"{value:.2f}{suffix}"


def _needs_mechanistic_workflow(result: StructuralResult) -> bool:
    if result.mechanistic_validation is not None:
        return False
    checks = (result.fatigue_check or "", result.rutting_check or "")
    return any(MECHANISTIC_WORKFLOW_NOT_RUN in text for text in checks)


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
        self._last_iitpave_workflow = None
        self._synchronized_values = {}
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
        self.btn_refresh = styled_button("Refresh From Previous Module", "secondary")
        self.btn_refresh.clicked.connect(self.refresh_from_source)
        self.header.add_action(self.btn_export)
        self.header.add_action(self.btn_refresh)
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

        self.chk_override = QCheckBox("Manual Override (Edit synchronized values)")
        self.chk_override.setStyleSheet("font-weight: bold; color: #7d6608;")
        self.chk_override.toggled.connect(self._on_override_toggled)

        self.txt_override_reason = QLineEdit()
        self.txt_override_reason.setPlaceholderText("Enter reason for manual override...")
        self.txt_override_reason.setVisible(False)

        self.lbl_override_badge = QLabel("⚠️ MANUAL OVERRIDE ACTIVE")
        self.lbl_override_badge.setStyleSheet(
            "background-color: #fde8e5; color: #d9381e; font-weight: bold; "
            "padding: 4px 8px; border-radius: 4px; border: 1px solid #d9381e;"
        )
        self.lbl_override_badge.setVisible(False)

        form.addRow("Road Category", self.road_cat)
        form.addRow("Design Life", self.design_life)
        form.addRow("Initial Commercial Traffic", self.cvpd)
        form.addRow("Traffic Growth Rate", self.growth)
        form.addRow("Vehicle Damage Factor (VDF)", self.vdf)
        form.addRow("Lane Distribution Factor (LDF)", self.ldf)
        form.addRow("Subgrade CBR (4-day soaked)", self.cbr)
        form.addRow("Resilient Modulus (optional)", self.mr_mpa)
        form.addRow("Workflow Override", self.chk_override)
        form.addRow("Override Reason", self.txt_override_reason)
        form.addRow("Override Status", self.lbl_override_badge)
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

        self.res_tabs = QTabWidget()
        rl.addWidget(self.res_tabs)

        # Tab 1: Composition & Strains
        self.tab_comp = QWidget()
        tl1 = QVBoxLayout(self.tab_comp)
        tl1.setContentsMargins(10, 10, 10, 10); tl1.setSpacing(10)
        
        self.layer_table = QTableWidget(0, 4)
        self.layer_table.setHorizontalHeaderLabels(
            ["Layer", "Material", "Thickness (mm)", "Modulus (MPa)"])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layer_table.verticalHeader().setVisible(False)
        tl1.addWidget(self.layer_table)

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("font-weight:bold; color:#1f3a68; font-size:11pt;")
        tl1.addWidget(self.lbl_total)

        self.lbl_mode_banner = QLabel("")
        self.lbl_mode_banner.setWordWrap(True)
        self.lbl_mode_banner.linkActivated.connect(self._on_banner_link_clicked)
        tl1.addWidget(self.lbl_mode_banner)

        self.lbl_checks = QLabel("")
        self.lbl_checks.setWordWrap(True)
        self.lbl_checks.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:10pt;")
        tl1.addWidget(self.lbl_checks)
        self.res_tabs.addTab(self.tab_comp, "Composition & Strains")

        # Tab 2: Engineering Traceability
        self.tab_trace = QWidget()
        tl2 = QVBoxLayout(self.tab_trace)
        tl2.setContentsMargins(10, 10, 10, 10); tl2.setSpacing(10)
        
        tl2.addWidget(QLabel("<b>Engineering Decision Chain</b>"))
        self.lbl_decision_chain = QLabel("—")
        self.lbl_decision_chain.setStyleSheet(
            "background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 4px; "
            "padding: 8px; color: #166534; font-size: 9.5pt;"
        )
        self.lbl_decision_chain.setWordWrap(True)
        tl2.addWidget(self.lbl_decision_chain)
        
        tl2.addWidget(QLabel("<b>Design Decision Tree Flow</b>"))
        self.txt_decision_tree = QLabel("—")
        self.txt_decision_tree.setStyleSheet(
            "font-family: 'Courier New', Courier, monospace; background-color: #f8f9fa; "
            "border: 1px solid #e9ecef; border-radius: 4px; padding: 10px; font-size: 9.5pt; color: #333;"
        )
        tl2.addWidget(self.txt_decision_tree)
        
        tl2.addWidget(QLabel("<b>IRC Reference Card</b>"))
        self.irc_ref_table = QTableWidget(0, 2)
        self.irc_ref_table.setHorizontalHeaderLabels(["Reference Parameter", "IRC Value / Citation"])
        self.irc_ref_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.irc_ref_table.verticalHeader().setVisible(False)
        self.irc_ref_table.setMaximumHeight(200)
        tl2.addWidget(self.irc_ref_table)
        self.res_tabs.addTab(self.tab_trace, "Engineering Traceability")

        # Tab 3: Candidate Comparisons
        self.tab_candidates = QWidget()
        tl3 = QVBoxLayout(self.tab_candidates)
        tl3.setContentsMargins(10, 10, 10, 10); tl3.setSpacing(10)
        
        tl3.addWidget(QLabel("<b>Candidate Design Comparison Table</b>"))
        self.candidate_table = QTableWidget(0, 7)
        self.candidate_table.setHorizontalHeaderLabels(
            ["Plate Option", "Total Thickness", "Estimated Cost", "Life (Years)", "Complexity", "Maintainability", "Safety Status"]
        )
        self.candidate_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.candidate_table.verticalHeader().setVisible(False)
        tl3.addWidget(self.candidate_table)
        
        tl3.addWidget(QLabel("<b>Why Not Rejection Reasonings</b>"))
        self.lbl_why_not = QLabel("—")
        self.lbl_why_not.setWordWrap(True)
        self.lbl_why_not.setStyleSheet(
            "background-color: #fff5f5; border: 1px solid #fed7d7; border-radius: 4px; "
            "padding: 10px; color: #9b1c1c; font-size: 9.5pt;"
        )
        tl3.addWidget(self.lbl_why_not)
        self.res_tabs.addTab(self.tab_candidates, "Candidate Design Comparison")

        # Tab 4: Consultancy & Summary
        self.tab_consultancy = QWidget()
        tl4 = QVBoxLayout(self.tab_consultancy)
        tl4.setContentsMargins(10, 10, 10, 10); tl4.setSpacing(12)
        
        # Confidence score card
        self.lbl_confidence = QLabel("—")
        self.lbl_confidence.setWordWrap(True)
        self.lbl_confidence.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 4px; "
            "padding: 10px; color: #1e3a8a; font-size: 10pt;"
        )
        tl4.addWidget(self.lbl_confidence)
        
        tl4.addWidget(QLabel("<b>Consultancy Remarks (DPR ready)</b>"))
        self.lbl_remarks = QLabel("—")
        self.lbl_remarks.setWordWrap(True)
        self.lbl_remarks.setStyleSheet(
            "background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px; "
            "padding: 10px; color: #374151; font-size: 10pt; font-style: italic; line-height: 1.4;"
        )
        tl4.addWidget(self.lbl_remarks)
        
        tl4.addWidget(QLabel("<b>Client Non-Technical Summary</b>"))
        self.lbl_client_summary = QLabel("—")
        self.lbl_client_summary.setWordWrap(True)
        self.lbl_client_summary.setStyleSheet(
            "background-color: #fafaf9; border: 1px solid #e7e5e4; border-radius: 4px; "
            "padding: 10px; color: #44403c; font-size: 9.5pt;"
        )
        tl4.addWidget(self.lbl_client_summary)
        
        tl4.addWidget(QLabel("<b>Layer-by-Layer Engineering Justification</b>"))
        self.lbl_layer_justifications = QLabel("—")
        self.lbl_layer_justifications.setWordWrap(True)
        self.lbl_layer_justifications.setStyleSheet(
            "background-color: #fdfaf2; border: 1px solid #f5ebd2; border-radius: 4px; "
            "padding: 10px; color: #6e520a; font-size: 9.5pt;"
        )
        tl4.addWidget(self.lbl_layer_justifications)
        
        self.res_tabs.addTab(self.tab_consultancy, "Remarks & Client Summary")
        
        self.res_card.setVisible(False)
        bl.addWidget(self.res_card)

        # ----- Engineering Health Check card -----
        self.health_card = Card()
        hl = QVBoxLayout(self.health_card)
        hl.setContentsMargins(20, 16, 20, 16); hl.setSpacing(8)
        
        self.lbl_health_title = QLabel("<b>Engineering Health Check</b>")
        self.lbl_health_title.setStyleSheet("font-size:11pt; color:#1f3a68;")
        hl.addWidget(self.lbl_health_title)
        
        score_layout = QHBoxLayout()
        self.lbl_health_score = QLabel("Engineering Screening Score: —")
        self.lbl_health_score.setStyleSheet("font-size:14pt; font-weight:bold; color:#1f3a68;")
        self.lbl_risk_level = QLabel("Risk Level: —")
        self.lbl_risk_level.setStyleSheet("font-size:10pt; font-weight:bold; padding:4px 8px; border-radius:4px;")
        score_layout.addWidget(self.lbl_health_score)
        score_layout.addWidget(self.lbl_risk_level)
        score_layout.addStretch(1)
        hl.addLayout(score_layout)
        
        self.lbl_health_warnings = QLabel("")
        self.lbl_health_warnings.setWordWrap(True)
        self.lbl_health_warnings.setStyleSheet(
            "background:#fbeee6; color:#a04000; padding:8px 12px; "
            "border:1px solid #f5cba7; border-radius:4px; font-size:9.5pt;")
        hl.addWidget(self.lbl_health_warnings)
        
        self.lbl_health_notes = QLabel("")
        self.lbl_health_notes.setWordWrap(True)
        self.lbl_health_notes.setStyleSheet(
            "color:#5d6d7e; font-size:9.5pt; font-style:italic;")
        hl.addWidget(self.lbl_health_notes)
        
        self.health_card.setVisible(False)
        bl.addWidget(self.health_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    # ----- project handling -----
    # ----- manual override handlers -----
    def _on_override_toggled(self, checked: bool) -> None:
        self.txt_override_reason.setVisible(checked)
        self.lbl_override_badge.setVisible(checked)
        self._update_fields_editable()
        if not checked:
            self.txt_override_reason.clear()
            self._apply_synchronized_values()

    def _update_fields_editable(self) -> None:
        is_editable = self.chk_override.isChecked()
        locked = False
        if self._project_id:
            p = self.db.get_project(self._project_id)
            if p and p.locked:
                locked = True

        if locked:
            self.chk_override.setEnabled(False)
            self.txt_override_reason.setEnabled(False)
            for w in (self.cvpd, self.growth, self.design_life, self.vdf, self.ldf, self.cbr, self.mr_mpa, self.road_cat):
                w.setEnabled(False)
        else:
            self.chk_override.setEnabled(True)
            self.txt_override_reason.setEnabled(is_editable)
            for w in (self.cvpd, self.growth, self.design_life, self.vdf, self.ldf, self.cbr, self.mr_mpa):
                w.setEnabled(is_editable)
            self.road_cat.setEnabled(True)

    def _apply_synchronized_values(self) -> None:
        if not self._synchronized_values:
            return
        self.cvpd.setValue(float(self._synchronized_values.get("cvpd", 2000.0)))
        self.growth.setValue(float(self._synchronized_values.get("growth", 7.5)))
        self.design_life.setValue(int(self._synchronized_values.get("design_life", 15)))
        self.vdf.setValue(float(self._synchronized_values.get("vdf", 2.5)))
        self.ldf.setValue(float(self._synchronized_values.get("ldf", 0.75)))
        self.cbr.setValue(float(self._synchronized_values.get("cbr", 5.0)))
        self.mr_mpa.setValue(float(self._synchronized_values.get("mr", 0.0)))

    def refresh_from_source(self, interactive: bool = True) -> None:
        if self._project_id is None:
            return
            
        status = self.db.get_module_sync_status(self._project_id, "structural")
        
        if status == "Out of Sync" or self.chk_override.isChecked():
            if self.chk_override.isChecked() and interactive:
                # Show Keeping Manual Values dialog
                msg = QMessageBox(self)
                msg.setWindowTitle("Sync Alert")
                msg.setText("Source values have changed, and manual overrides are active on this page.\n\nChoose how to proceed:")
                keep_btn = msg.addButton("Keep Manual Values", QMessageBox.AcceptRole)
                reload_btn = msg.addButton("Reload Source Values", QMessageBox.DestructiveRole)
                cancel_btn = msg.addButton(QMessageBox.Cancel)
                msg.exec_()
                
                if msg.clickedButton() == keep_btn:
                    # Mark synced but keep manual override values active
                    self.db.mark_module_synced(self._project_id, "structural", ["traffic", "subgrade"])
                    self.db.log_project_audit(self._project_id, "structural", "Refresh", "User chose to keep manual overrides during sync refresh.")
                    
                    # Refresh main window status badge
                    parent = self.parent()
                    while parent is not None:
                        if hasattr(parent, "refresh_project_status_badge"):
                            parent.refresh_project_status_badge()
                            break
                        parent = parent.parent()
                        
                    QMessageBox.information(self, "Status Synced", "Manual values kept. Synchronization status marked as Synced.")
                    return
                elif msg.clickedButton() == reload_btn:
                    # Reload latest source values
                    self.db.log_project_audit(self._project_id, "structural", "Refresh", "User chose to reload source values, clearing overrides.")
                    self.chk_override.blockSignals(True)
                    self.chk_override.setChecked(False)
                    self.txt_override_reason.clear()
                    self.txt_override_reason.setVisible(False)
                    self.lbl_override_badge.setVisible(False)
                    self.chk_override.blockSignals(False)
                    
                    # Reload from DB and compute/save
                    self.set_project(self._project_id, self.proj_banner.text())
                    self._on_compute()
                    self._on_save()
                    return
                else:
                    # Cancel
                    return
            else:
                # No manual override active or non-interactive reload, simply reload
                self.db.log_project_audit(self._project_id, "structural", "Refresh", "Source values reloaded (no overrides active).")
                self.set_project(self._project_id, self.proj_banner.text())
                self._on_compute()
                self._on_save()
                if interactive:
                    QMessageBox.information(self, "Refreshed", "Source values reloaded successfully.")
        else:
            if interactive:
                ans = QMessageBox.question(
                    self, "Sync Status",
                    "Module is already Synced. Do you want to reload all source values from the database anyway?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    self.chk_override.setChecked(False)
                    self.set_project(self._project_id, self.proj_banner.text())
                    self._on_compute()
                    self._on_save()

    # ----- project handling -----
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last_result = None
        self._last_iitpave_workflow = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        self.health_card.setVisible(False)
        self.chk_override.blockSignals(True)
        self.chk_override.setChecked(False)
        self.txt_override_reason.clear()
        self.txt_override_reason.setVisible(False)
        self.lbl_override_badge.setVisible(False)
        self.chk_override.blockSignals(False)

        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")

        # 1. Fetch synchronized values from DB
        import json
        self._synchronized_values = {
            "cvpd": 2000.0,
            "growth": 7.5,
            "design_life": 15,
            "vdf": 2.5,
            "ldf": 0.75,
            "cbr": 5.0,
            "mr": 0.0,
        }

        # Subgrade from project record
        p = self.db.get_project(pid)
        if p:
            if p.subgrade_cbr is not None:
                self._synchronized_values["cbr"] = float(p.subgrade_cbr)
            if p.subgrade_mr is not None:
                self._synchronized_values["mr"] = float(p.subgrade_mr)

        # Traffic from traffic analysis
        ta = self.db.latest_traffic_analysis(pid)
        if ta:
            try:
                ta_in = json.loads(ta.inputs_json) if isinstance(ta.inputs_json, str) else ta.inputs_json
                if ta_in:
                    self._synchronized_values["cvpd"] = float(ta_in.get("initial_cvpd", 2000.0))
                    self._synchronized_values["growth"] = float(ta_in.get("growth_rate_pct", 7.5))
                    self._synchronized_values["design_life"] = int(ta_in.get("design_life_years", 15))
                
                ta_res = json.loads(ta.results_json) if isinstance(ta.results_json, str) else ta.results_json
                if ta_res:
                    self._synchronized_values["vdf"] = float(ta_res.get("vdf_used", 2.5))
                    self._synchronized_values["ldf"] = float(ta_res.get("ldf_used", 0.75))
            except Exception:
                pass

        # 2. Check if a saved structural design exists
        sd = self.db.latest_structural_design(pid)
        self.btn_export.setEnabled(sd is not None)
        
        has_override = False
        loaded_inputs = {}
        if sd and sd.inputs_json:
            try:
                loaded_inputs = json.loads(sd.inputs_json) if isinstance(sd.inputs_json, str) else sd.inputs_json
                overrides_data = loaded_inputs.get("overrides", {})
                if overrides_data.get("active"):
                    has_override = True
                    self.chk_override.blockSignals(True)
                    self.chk_override.setChecked(True)
                    self.txt_override_reason.setText(overrides_data.get("reason", ""))
                    self.txt_override_reason.setVisible(True)
                    self.lbl_override_badge.setVisible(True)
                    self.chk_override.blockSignals(False)
            except Exception:
                pass

        if has_override:
            # Load user-modified values from the saved structural design
            self.road_cat.setCurrentText(loaded_inputs.get("road_category", "NH / SH"))
            self.design_life.setValue(int(loaded_inputs.get("design_life_years", 15)))
            self.cvpd.setValue(float(loaded_inputs.get("initial_cvpd", 2000)))
            self.growth.setValue(float(loaded_inputs.get("growth_rate_pct", 7.5)))
            self.vdf.setValue(float(loaded_inputs.get("vdf", 2.5)))
            self.ldf.setValue(float(loaded_inputs.get("ldf", 0.75)))
            self.cbr.setValue(float(loaded_inputs.get("subgrade_cbr_pct", 5.0)))
            self.mr_mpa.setValue(float(loaded_inputs.get("resilient_modulus_mpa") or 0.0))
        else:
            # Populate fields from the synchronized database values
            if sd and sd.inputs_json:
                self.road_cat.setCurrentText(loaded_inputs.get("road_category", "NH / SH"))
            self._apply_synchronized_values()

        self._update_fields_editable()

    def _collect(self) -> StructuralInput:
        mr = self.mr_mpa.value()
        overrides_dict = {}
        
        if self.chk_override.isChecked():
            overrides_dict["active"] = True
            overrides_dict["reason"] = self.txt_override_reason.text().strip()
            overrides_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            values_overridden = {}
            fields_map = {
                "initial_cvpd": ("cvpd", self.cvpd.value()),
                "growth_rate_pct": ("growth", self.growth.value()),
                "design_life_years": ("design_life", self.design_life.value()),
                "vdf": ("vdf", self.vdf.value()),
                "ldf": ("ldf", self.ldf.value()),
                "subgrade_cbr_pct": ("cbr", self.cbr.value()),
                "resilient_modulus_mpa": ("mr", self.mr_mpa.value()),
            }
            for db_field, (sync_key, val) in fields_map.items():
                sync_val = self._synchronized_values.get(sync_key)
                if sync_val is not None and abs(val - float(sync_val)) > 1e-4:
                    values_overridden[db_field] = {
                        "original": sync_val,
                        "manual": val,
                        "timestamp": overrides_dict["timestamp"],
                        "reason": overrides_dict["reason"],
                        "field_name": db_field
                    }
            overrides_dict["values"] = values_overridden

        return StructuralInput(
            road_category=self.road_cat.currentText(),
            design_life_years=self.design_life.value(),
            initial_cvpd=self.cvpd.value(),
            growth_rate_pct=self.growth.value(),
            vdf=self.vdf.value(),
            ldf=self.ldf.value(),
            subgrade_cbr_pct=self.cbr.value(),
            resilient_modulus_mpa=(mr if mr > 0 else None),
            overrides=overrides_dict,
        )

    # ----- compute / save -----
    def _on_compute(self) -> None:
        try:
            inp = self._collect()
            result = compute_structural_design(inp)
            workflow = None
            if _needs_mechanistic_workflow(result):
                workflow = run_structural_iitpave_mechanistic_workflow(result)
                result = workflow.structural_result
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last_result = result
        self._last_iitpave_workflow = workflow
        self._render(result)
        self.btn_save.setEnabled(self._project_id is not None)

    def _render(self, r: StructuralResult) -> None:
        if _needs_mechanistic_workflow(r):
            try:
                workflow = run_structural_iitpave_mechanistic_workflow(r)
                r = workflow.structural_result
                self._last_result = r
                self._last_iitpave_workflow = workflow
            except Exception as e:
                r = dataclasses.replace(
                    r,
                    fatigue_check=f"IITPAVE unavailable - {e}",
                    rutting_check=f"IITPAVE unavailable - {e}",
                )
                self._last_result = r
        self.res_card.setVisible(True)
        self.lbl_msa.setText(f"Design Traffic = {r.design_msa:.2f} MSA")
        self.lbl_meta.setText(
            f"Growth factor = {r.growth_factor:.2f}  ·  "
            f"Subgrade Mr = {r.subgrade_mr_mpa:.1f} MPa"
        )
        
        # Populate Tab 1: Composition & Strains
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
        
        # Determine and display active validation mode banner
        mode = r.validation_mode
        is_mock = False
        if r.mechanistic_validation and "Demo verification example only" in (r.mechanistic_validation.notes or ""):
            is_mock = True
            
        if is_mock:
            banner_style = "background-color:#fadbd8; color:#78281f; font-weight:bold; border:1px solid #f5b7b1; border-radius:4px; padding:6px 12px; font-size:10pt;"
            banner_text = (
                "⚠️ <b>Verification Mode:</b> Decision Support Mode (Demo Run)<br>"
                "<b>Demo verification example only — not actual IITPAVE execution.</b>"
            )
        elif mode == "Mechanistic Verified Mode":
            banner_style = "background-color:#d4efdf; color:#196f3d; font-weight:bold; border:1px solid #a3e4d7; border-radius:4px; padding:6px 12px; font-size:10pt;"
            banner_text = (
                f"🛡️ <b>Verification Mode:</b> {mode}<br>"
                "Verified using real local IITPAVE execution. "
                "Design strains conform to IRC:37 fatigue/rutting specifications."
            )
        else:
            banner_style = "background-color:#fef9e7; color:#7d6608; border:1px solid #f9e79f; border-radius:4px; padding:6px 12px; font-size:10pt;"
            banner_text = (
                f"ℹ️ <b>Verification Mode:</b> {mode}<br>"
                "This design is computed under Decision Support Mode. "
                "IITPAVE mechanistic verification has not been performed or is using default stubs/placeholders. "
                "To verify the design with IITPAVE.exe, configure the executable path in the "
                "<a href='#iitpave_settings' style='color:#1a5276; font-weight:bold;'>IITPAVE Integration Manager</a>."
            )
        self.lbl_mode_banner.setStyleSheet(banner_style)
        self.lbl_mode_banner.setText(banner_text)

        mech = r.mechanistic_validation
        if mech is not None:
            self.lbl_checks.setText(
                f"Fatigue check: {r.fatigue_check}<br>"
                f"Rutting check: {r.rutting_check}<br>"
                f"epsilon_t = {_fmt_mech_value(mech.fatigue.epsilon_t_microstrain)} "
                f"microstrain; NF = {_fmt_mech_value(mech.fatigue.cumulative_life_msa)} "
                f"MSA<br>"
                f"epsilon_v = {_fmt_mech_value(mech.rutting.epsilon_v_microstrain)} "
                f"microstrain; NR = {_fmt_mech_value(mech.rutting.cumulative_life_msa)} "
                f"MSA<br>"
                f"<i>{r.notes}</i>"
            )
        else:
            self.lbl_checks.setText(
                f"Fatigue check: {r.fatigue_check}<br>"
                f"Rutting check: {r.rutting_check}<br>"
                f"<i>{r.notes}</i>"
            )

        # Explainable Design Data Binding
        import json
        log_dict = None
        if hasattr(r, "traceability_log_json") and r.traceability_log_json:
            try:
                log_dict = json.loads(r.traceability_log_json)
            except Exception:
                pass
                
        if not log_dict:
            from app.core.explainable_design import generate_explainable_details
            log_dict = generate_explainable_details(r, self.db, self._project_id)
            
        # 1. Populating Tab 2: Traceability
        chain_parts = [
            f"<b>Traffic Category:</b> {log_dict.get('traffic_category', '—')}",
            f"<b>Subgrade Range:</b> {log_dict.get('cbr_category', '—')}",
            f"<b>Selected Plate:</b> {log_dict.get('final_selection', {}).get('reference_plate', '—')}",
            f"<b>IITPAVE Status:</b> {log_dict.get('mechanistic_verification', '—')}",
            f"<b>Cost:</b> {log_dict.get('client_summary', {}).get('estimated_cost', '—')}"
        ]
        self.lbl_decision_chain.setText(" ➔ ".join(chain_parts))
        self.txt_decision_tree.setText(log_dict.get("decision_tree_ascii", "—"))
        
        irc = log_dict.get("irc_ref_card", {})
        ref_rows = [
            ["IRC Standard Citation", irc.get("standard", "—")],
            ["Edition / Version", irc.get("edition", "—")],
            ["Governing Catalogue Table", irc.get("table_number", "—")],
            ["Governing Catalogue Figure", irc.get("figure_number", "—")],
            ["Selected Design Plate", irc.get("plate_number", "—")],
            ["CBR Range Specification", irc.get("cbr_range", "—")],
            ["Design Traffic Limit", irc.get("traffic_range", "—")],
            ["Standard Clauses", irc.get("governing_clause", "—")]
        ]
        self.irc_ref_table.setRowCount(len(ref_rows))
        for row_idx, (k, v) in enumerate(ref_rows):
            it_k = QTableWidgetItem(k)
            it_v = QTableWidgetItem(v)
            self.irc_ref_table.setItem(row_idx, 0, it_k)
            self.irc_ref_table.setItem(row_idx, 1, it_v)

        # 2. Populating Tab 3: Candidates
        candidates_list = log_dict.get("candidates", [])
        self.candidate_table.setRowCount(len(candidates_list))
        recommended_plate = log_dict.get("final_selection", {}).get("reference_plate", "")
        
        for row_idx, cand in enumerate(candidates_list):
            name_val = cand.get("name", "—")
            is_rec = (name_val == recommended_plate)
            if is_rec:
                name_val += " (RECOMMENDED)"
                
            cells = [
                name_val,
                f"{cand.get('total_thickness_mm', 0):.0f} mm",
                f"Rs. {cand.get('estimated_cost', 0):,.2f}",
                f"{cand.get('expected_life_years', 0):g} years",
                cand.get("construction_complexity", "—"),
                cand.get("maintainability", "—"),
                cand.get("mechanistic_status", "—")
            ]
            for col_idx, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                if is_rec:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.candidate_table.setItem(row_idx, col_idx, it)
                
        rejections = log_dict.get("rejected_options", [])
        if rejections:
            why_not_html = "<br>".join(
                f"<b>• {rej['name']}:</b> {rej['reason']}" for rej in rejections
            )
        else:
            why_not_html = "<i>No candidate options were rejected; the recommended design satisfies all standard constraints.</i>"
        self.lbl_why_not.setText(why_not_html)

        # 3. Populating Tab 4: Consultancy & Summary
        conf_score = log_dict.get("confidence_score", 100.0)
        breakdown = log_dict.get("confidence_breakdown", {})
        bd_text = "<br>".join(f"  - {k}: {v:.0f}%" for k, v in breakdown.items())
        self.lbl_confidence.setText(
            f"<b>Overall Engineering Confidence: {conf_score}%</b><br>"
            f"<b>Confidence Score Component Breakdown:</b><br>{bd_text}"
        )
        
        self.lbl_remarks.setText(log_dict.get("engineering_remarks", "—"))
        
        cli = log_dict.get("client_summary", {})
        cli_html = (
            f"<b>Recommended Pavement:</b> {cli.get('recommended_pavement', '—')}<br>"
            f"<b>Expected Design Life:</b> {cli.get('expected_design_life', '—')}<br>"
            f"<b>Mechanistic Verification:</b> {cli.get('mechanistic_verified', '—')}<br>"
            f"<b>IRC Compliance:</b> {cli.get('irc_compliant', '—')}<br>"
            f"<b>Construction Readiness:</b> {cli.get('construction_ready', '—')}<br>"
            f"<b>Estimated Pavement Cost (per km lane):</b> {cli.get('estimated_cost', '—')}<br>"
            f"<b>Maintenance Expectations:</b> {cli.get('maintenance_expectation', '—')}"
        )
        self.lbl_client_summary.setText(cli_html)
        
        justs = log_dict.get("layer_justifications", [])
        just_html = "<br>".join(
            f"<b>• {j['name']} ({j['thickness']}):</b> {j['reason']}" for j in justs
        )
        self.lbl_layer_justifications.setText(just_html)

        # Render Engineering Health Check Card
        if hasattr(r, "intelligence") and r.intelligence:
            intel = r.intelligence
            self.health_card.setVisible(True)
            self.lbl_health_score.setText(f"Engineering Screening Score: {intel.health_score:.0f}/100")
            self.lbl_risk_level.setText(intel.risk_level)
            
            if "high" in intel.risk_level.lower():
                self.lbl_risk_level.setStyleSheet("background:#f9d5d5; color:#a81f1f; font-size:10pt; font-weight:bold; padding:4px 8px; border-radius:4px;")
            elif "review" in intel.risk_level.lower():
                self.lbl_risk_level.setStyleSheet("background:#fef5d1; color:#a67c00; font-size:10pt; font-weight:bold; padding:4px 8px; border-radius:4px;")
            elif "acceptable" in intel.risk_level.lower():
                self.lbl_risk_level.setStyleSheet("background:#d4efdf; color:#196f3d; font-size:10pt; font-weight:bold; padding:4px 8px; border-radius:4px;")
            else:
                self.lbl_risk_level.setStyleSheet("background:#d4e6f1; color:#1a5276; font-size:10pt; font-weight:bold; padding:4px 8px; border-radius:4px;")
                
            if intel.warnings:
                self.lbl_health_warnings.setVisible(True)
                self.lbl_health_warnings.setText("<br>".join(f"⚠️ {w}" for w in intel.warnings))
            else:
                self.lbl_health_warnings.setVisible(False)
                
            if intel.review_notes:
                self.lbl_health_notes.setVisible(True)
                self.lbl_health_notes.setText("<br>".join(f"• {n}" for n in intel.review_notes))
            else:
                self.lbl_health_notes.setVisible(False)
        else:
            self.health_card.setVisible(False)

    def _on_banner_link_clicked(self) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_show_page"):
                parent._show_page("iitpave_status")
                break
            parent = parent.parent()

    def _save_override_history_entries(self) -> None:
        if not self._project_id or not self._last_result:
            return
        
        if not self.chk_override.isChecked():
            return
            
        reason = self.txt_override_reason.text().strip()
        if not reason:
            reason = "No reason specified"
            
        # Get previous saved inputs
        sd_prev = self.db.latest_structural_design(self._project_id)
        prev_inputs = {}
        if sd_prev and sd_prev.inputs_json:
            try:
                prev_inputs = json.loads(sd_prev.inputs_json) if isinstance(sd_prev.inputs_json, str) else sd_prev.inputs_json
            except Exception:
                pass
                
        fields_map = {
            "initial_cvpd": ("cvpd", self.cvpd.value()),
            "growth_rate_pct": ("growth", self.growth.value()),
            "design_life_years": ("design_life", self.design_life.value()),
            "vdf": ("vdf", self.vdf.value()),
            "ldf": ("ldf", self.ldf.value()),
            "subgrade_cbr_pct": ("cbr", self.cbr.value()),
            "resilient_modulus_mpa": ("mr", self.mr_mpa.value()),
        }
        
        for db_field, (sync_key, val) in fields_map.items():
            sync_val = self._synchronized_values.get(sync_key)
            if sync_val is not None and abs(val - float(sync_val)) > 1e-4:
                prev_val = prev_inputs.get(db_field)
                if prev_val is None:
                    prev_val = sync_val
                
                # Check if it changed from previous or if first save
                if abs(float(prev_val) - val) > 1e-4 or not sd_prev:
                    self.db.append_override_history(
                        project_id=self._project_id,
                        field_name=db_field,
                        original_val=sync_val,
                        previous_val=prev_val,
                        new_val=val,
                        reason=reason,
                        module_name="Structural",
                        user="Engineer"
                    )
                    self.db.log_project_audit(
                        self._project_id,
                        "structural",
                        "Manual Override",
                        f"Field '{db_field}' overridden from {sync_val} to {val}. Reason: {reason}"
                    )

    def _on_save(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        try:
            self._save_override_history_entries()
            self.db.save_structural_design(
                project_id=self._project_id, result=self._last_result
            )
            if self._last_result.mechanistic_validation is not None:
                self.db.save_mechanistic_validation(
                    project_id=self._project_id,
                    summary=self._last_result.mechanistic_validation,
                    inputs=(
                        self._last_iitpave_workflow.as_dict()
                        if self._last_iitpave_workflow is not None
                        else None
                    ),
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
