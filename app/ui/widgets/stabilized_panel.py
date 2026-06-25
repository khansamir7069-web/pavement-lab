"""Cement-Treated Stabilized Pavement (CTB/CTS) Design Wizard UI."""
from __future__ import annotations

import dataclasses
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    StabilizedInput,
    StabilizedResult,
    compute_stabilized_design,
    run_stabilized_iitpave_mechanistic_workflow,
)
from app.reports.stabilized_report import (
    StabilizedReportContext,
    build_stabilized_docx,
)
from .common import Card, PageHeader, styled_button


def _spin(value: float, lo: float, hi: float, step: float,
           decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(f" {suffix}")
    return sp


class StabilizedPanel(QWidget):
    """Wizard UI for Cement-Treated Base/Sub-base stabilized pavement."""

    saved = Signal(int)              # emits project_id after save
    export_requested = Signal(int)   # emits project_id for Word report export

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last_result: StabilizedResult | None = None
        self._last_iitpave_workflow = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Stabilized Pavement Wizard",
            "IRC:37 — Cement-Treated Base (CTB) & Cement-Treated Sub-base (CTS) comparison"
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

        # Project Banner
        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:8px 12px; "
            "border:1px solid #c9d6ec; border-radius:4px;")
        bl.addWidget(self.proj_banner)

        # Inputs Card
        in_card = Card()
        form = QFormLayout(in_card)
        form.setContentsMargins(20, 16, 20, 16); form.setSpacing(8)

        # Baseline parameters
        self.flex_msa = _spin(10.0, 0.1, 500.0, 1.0, 2, "MSA")
        self.flex_cbr = _spin(5.0, 0.5, 50.0, 0.5, 1, "%")

        # CTB layer
        self.ctb_thick = _spin(100.0, 10.0, 400.0, 10.0, 0, "mm")
        self.ctb_modulus = _spin(5000.0, 100.0, 30000.0, 500.0, 0, "MPa")
        self.ctb_ucs = _spin(4.5, 0.0, 20.0, 0.5, 1, "MPa")
        self.ctb_ucs.setSpecialValueText(" (0.0 = Missing UCS)")
        self.ctb_poisson = _spin(0.25, 0.01, 0.49, 0.05, 2)

        # CTS layer
        self.cts_class = QComboBox()
        for c in ("C1.5/2.0", "C3/4", "C5/6", "Other"):
            self.cts_class.addItem(c)
        self.cts_thick = _spin(100.0, 10.0, 400.0, 10.0, 0, "mm")
        self.cts_modulus = _spin(3000.0, 100.0, 20000.0, 500.0, 0, "MPa")
        self.cts_poisson = _spin(0.25, 0.01, 0.49, 0.05, 2)

        # Auxiliary layers
        self.bit_thick = _spin(100.0, 10.0, 300.0, 10.0, 0, "mm")
        self.gsb_thick = _spin(150.0, 10.0, 400.0, 10.0, 0, "mm")

        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Engineer remarks or design assumptions...")

        form.addRow("<b>Baseline Design Traffic</b>", self.flex_msa)
        form.addRow("<b>Baseline Subgrade CBR</b>", self.flex_cbr)
        form.addRow(QLabel("<hr>"))
        form.addRow("<b>CTB Thickness</b>", self.ctb_thick)
        form.addRow("<b>CTB Modulus</b>", self.ctb_modulus)
        form.addRow("<b>CTB UCS Strength (28-day)</b>", self.ctb_ucs)
        form.addRow("<b>CTB Poisson's Ratio</b>", self.ctb_poisson)
        form.addRow(QLabel("<hr>"))
        form.addRow("<b>CTS Strength Class</b>", self.cts_class)
        form.addRow("<b>CTS Thickness</b>", self.cts_thick)
        form.addRow("<b>CTS Modulus</b>", self.cts_modulus)
        form.addRow("<b>CTS Poisson's Ratio</b>", self.cts_poisson)
        form.addRow(QLabel("<hr>"))
        form.addRow("<b>Bituminous Cover Thickness</b>", self.bit_thick)
        form.addRow("<b>Granular Sub-base Thickness</b>", self.gsb_thick)
        form.addRow("<b>Remarks / Notes</b>", self.notes)

        bl.addWidget(in_card)

        # Results Card
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(8)
        
        rl.addWidget(QLabel("<b>Computed Results & Comparison</b>"))

        # Validation Mode + safety
        self.lbl_mode = QLabel("Validation Mode: —")
        self.lbl_mode.setWordWrap(True)
        self.lbl_mode.linkActivated.connect(self._on_banner_link_clicked)
        self.lbl_mode.setStyleSheet("font-size:12pt; font-weight:bold; color:#1f3a68;")
        rl.addWidget(self.lbl_mode)
        
        self.lbl_safety = QLabel("")
        self.lbl_safety.setStyleSheet("color:#b02525; font-size:10pt; font-weight:bold; padding:4px;")
        self.lbl_safety.setWordWrap(True)
        rl.addWidget(self.lbl_safety)

        # Table comparing structures side-by-side
        self.comp_table = QTableWidget(0, 2)
        self.comp_table.setHorizontalHeaderLabels([
            "Conventional Flexible Catalogue", 
            "Cement-Stabilized Design (CTB/CTS)"
        ])
        self.comp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comp_table.verticalHeader().setVisible(False)
        rl.addWidget(self.comp_table)

        self.lbl_savings = QLabel("Thickness Savings: —")
        self.lbl_savings.setStyleSheet("font-size:13pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_savings)
        
        self.lbl_savings_label = QLabel("")
        self.lbl_savings_label.setStyleSheet("color:#6a7180; font-size:9pt; italic:true;")
        rl.addWidget(self.lbl_savings_label)

        # Warnings panel
        self.lbl_warnings = QLabel("")
        self.lbl_warnings.setWordWrap(True)
        self.lbl_warnings.setStyleSheet(
            "background:#fbf2d3; color:#6e520a; padding:8px 12px; "
            "border:1px solid #e8d68f; border-radius:4px; font-size:9.5pt;")
        rl.addWidget(self.lbl_warnings)

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

        # ----- Pavement Alternative Selection Panel -----
        self.options_card = Card()
        ol = QVBoxLayout(self.options_card)
        ol.setContentsMargins(20, 16, 20, 16); ol.setSpacing(8)
        
        self.lbl_options_title = QLabel("<b>Pavement Alternative Selection System</b>")
        self.lbl_options_title.setStyleSheet("font-size:11.5pt; color:#1f3a68;")
        ol.addWidget(self.lbl_options_title)

        # Options comparison table
        self.options_table = QTableWidget(0, 7)
        self.options_table.setHorizontalHeaderLabels([
            "Option",
            "Thickness",
            "Layers",
            "Approx Cost Index",
            "Engineering Score",
            "IITPAVE Status",
            "Recommendation"
        ])
        self.options_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.options_table.verticalHeader().setVisible(False)
        self.options_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.options_table.setSelectionMode(QTableWidget.SingleSelection)
        self.options_table.setMinimumHeight(180)
        ol.addWidget(self.options_table)

        # Smart recommendation text label
        self.lbl_smart_rec = QLabel("")
        self.lbl_smart_rec.setWordWrap(True)
        self.lbl_smart_rec.setStyleSheet(
            "background:#eafaf1; color:#1b5e20; padding:8px 12px; "
            "border:1px solid #c8e6c9; border-radius:4px; font-size:9.5pt; font-style:italic;"
        )
        self.lbl_smart_rec.setVisible(False)
        ol.addWidget(self.lbl_smart_rec)

        # Actions buttons layout
        btn_layout = QHBoxLayout()
        self.btn_gen_options = styled_button("Generate Options", "secondary")
        self.btn_gen_options.clicked.connect(self._on_generate_options)
        self.btn_mark_selected = styled_button("Mark As Selected Design", "primary")
        self.btn_mark_selected.clicked.connect(self._on_mark_selected)
        self.btn_mark_selected.setEnabled(False)
        btn_layout.addWidget(self.btn_gen_options)
        btn_layout.addWidget(self.btn_mark_selected)
        btn_layout.addStretch(1)
        ol.addLayout(btn_layout)

        bl.addWidget(self.options_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)


    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last_result = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        self.health_card.setVisible(False)
        
        # Reset Options Table
        self.options_table.setRowCount(0)
        self.lbl_smart_rec.setVisible(False)
        self.btn_mark_selected.setEnabled(False)

        if pid is None:
            self.proj_banner.setText("⚠ No project loaded.")
            self.btn_export.setEnabled(False)
            return

        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        
        # 1. Try to load saved stabilized design
        row = self.db.latest_stabilized_design(pid)
        self.btn_export.setEnabled(row is not None)
        
        # 2. Try to pre-fill baseline CBR and MSA from conventional structural design
        sd_conv = self.db.latest_structural_design(pid)
        if sd_conv:
            self.flex_msa.setValue(float(sd_conv.design_msa or 10.0))
            if sd_conv.inputs_json:
                try:
                    d_conv = json.loads(sd_conv.inputs_json)
                    self.flex_cbr.setValue(float(d_conv.get("subgrade_cbr_pct", 5.0)))
                except Exception:
                    pass

        # 3. If saved stabilized design exists, populate fields
        if row and row.inputs_json:
            try:
                d = json.loads(row.inputs_json)
                self.ctb_thick.setValue(float(d.get("ctb_thickness_mm", 100.0)))
                self.ctb_modulus.setValue(float(d.get("ctb_modulus_mpa", 5000.0)))
                self.ctb_ucs.setValue(float(d.get("ctb_ucs_mpa", 4.5)))
                self.ctb_poisson.setValue(float(d.get("ctb_poisson", 0.25)))
                
                self.cts_class.setCurrentText(d.get("cts_class", "C1.5/2.0"))
                self.cts_thick.setValue(float(d.get("cts_thickness_mm", 100.0)))
                self.cts_modulus.setValue(float(d.get("cts_modulus_mpa", 3000.0)))
                self.cts_poisson.setValue(float(d.get("cts_poisson", 0.25)))
                
                self.bit_thick.setValue(float(d.get("bituminous_thickness_mm", 100.0)))
                self.gsb_thick.setValue(float(d.get("gsb_thickness_mm", 150.0)))
                self.flex_msa.setValue(float(d.get("flexible_design_msa", 10.0)))
                self.flex_cbr.setValue(float(d.get("flexible_subgrade_cbr", 5.0)))
                self.notes.setText(d.get("notes", ""))
                
                # Auto-run compute to display results
                self._on_compute()
            except Exception:
                pass

        # Auto-generate options comparison for alternative selection stage
        self._on_generate_options()


    def _collect(self) -> StabilizedInput:
        return StabilizedInput(
            ctb_thickness_mm=self.ctb_thick.value(),
            ctb_modulus_mpa=self.ctb_modulus.value(),
            ctb_ucs_mpa=self.ctb_ucs.value(),
            ctb_poisson=self.ctb_poisson.value(),
            cts_class=self.cts_class.currentText(),
            cts_thickness_mm=self.cts_thick.value(),
            cts_modulus_mpa=self.cts_modulus.value(),
            cts_poisson=self.cts_poisson.value(),
            bituminous_thickness_mm=self.bit_thick.value(),
            gsb_thickness_mm=self.gsb_thick.value(),
            flexible_design_msa=self.flex_msa.value(),
            flexible_subgrade_cbr=self.flex_cbr.value(),
            notes=self.notes.text().strip(),
        )

    def _on_compute(self) -> None:
        try:
            inp = self._collect()
            res = compute_stabilized_design(inp, has_mechanistic_validation=False)
            
            workflow = None
            try:
                workflow = run_stabilized_iitpave_mechanistic_workflow(res)
                res = workflow.structural_result
            except Exception as e:
                # We remain in Decision Support Mode as required if execution or parser fails
                res = dataclasses.replace(
                    res,
                    validation_mode="Decision Support Mode",
                    mechanistic_validation=None,
                )
            
            self._last_result = res
            self._last_iitpave_workflow = workflow
            self._render(res)
            self.btn_save.setEnabled(self._project_id is not None)
        except Exception as e:
            QMessageBox.critical(self, "Invalid Inputs", str(e))

    def _render(self, r: StabilizedResult) -> None:
        self.res_card.setVisible(True)
        
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
                "Stabilized pavement design strains conform to specifications."
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
        self.lbl_mode.setStyleSheet(banner_style)
        self.lbl_mode.setText(banner_text)
        self.lbl_safety.setText(f"⚠ {r.safety_disclaimer}")

        # Render composition table side-by-side
        self.comp_table.setRowCount(0)
        max_rows = max(len(r.conventional_composition), len(r.stabilized_composition))
        self.comp_table.setRowCount(max_rows + 1) # +1 for total row

        for i in range(max_rows):
            # Conventional cell
            if i < len(r.conventional_composition):
                ly = r.conventional_composition[i]
                c_text = f"{ly.name} ({ly.material}): {ly.thickness_mm:.0f} mm"
            else:
                c_text = "—"
            
            # Stabilized cell
            if i < len(r.stabilized_composition):
                ly = r.stabilized_composition[i]
                s_text = f"{ly.name} ({ly.material}): {ly.thickness_mm:.0f} mm"
            else:
                s_text = "—"

            self.comp_table.setItem(i, 0, QTableWidgetItem(c_text))
            self.comp_table.setItem(i, 1, QTableWidgetItem(s_text))

        # Total depth row
        t_flex = sum(ly.thickness_mm for ly in r.conventional_composition)
        t_stab = sum(ly.thickness_mm for ly in r.stabilized_composition)
        
        self.comp_table.setItem(max_rows, 0, QTableWidgetItem(f"TOTAL: {t_flex:.0f} mm"))
        self.comp_table.setItem(max_rows, 1, QTableWidgetItem(f"TOTAL: {t_stab:.0f} mm"))

        # Thickness savings
        self.lbl_savings.setText(
            f"Thickness Savings: {r.thickness_savings_mm:.0f} mm ({r.thickness_savings_pct:.1f}% reduction)"
        )
        self.lbl_savings_label.setText(r.comparison_label)

        # Warnings
        if r.warnings:
            self.lbl_warnings.setText("<b>Screening Alerts:</b><br>• " + "<br>• ".join(r.warnings))
            self.lbl_warnings.setVisible(True)
        else:
            self.lbl_warnings.setVisible(False)

        if hasattr(r, 'intelligence') and r.intelligence:
            intel = r.intelligence
            self.health_card.setVisible(True)
            self.lbl_health_score.setText(f"Engineering Screening Score: {intel.health_score:.0f}/100")
            self.lbl_risk_level.setText(intel.risk_level)
            
            # Style risk level badge
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

    def _on_save(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        try:
            self.db.save_stabilized_design(
                project_id=self._project_id,
                result=self._last_result,
            )
            # Persist mechanistic validation summary if completed successfully
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
            # Mark module complete in Project.modules_json
            self.db.update_module_status(self._project_id, "stabilized", "complete")
            
            self.btn_export.setEnabled(True)
            self.saved.emit(self._project_id)
            self.notes.setText(self._last_result.inputs.notes)
            QMessageBox.information(self, "Success", "Stabilized design saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_banner_link_clicked(self) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_show_page"):
                parent._show_page("iitpave_status")
                break
            parent = parent.parent()

    def _on_export(self) -> None:
        if self._project_id is None or self._last_result is None:
            return
        self.export_requested.emit(self._project_id)

    def _on_generate_options(self) -> None:
        if self._project_id is None:
            return
        
        from app.engineering.option_engine import generate_pavement_options
        options = generate_pavement_options(self._project_id, self.db)
        if not options:
            self.options_table.setRowCount(0)
            self.lbl_smart_rec.setVisible(False)
            return

        self.options_table.setRowCount(0)
        self.options_table.setRowCount(len(options))

        for row_idx, opt in enumerate(options):
            # Option Name
            item_name = QTableWidgetItem(opt["option_name"])
            self.options_table.setItem(row_idx, 0, item_name)

            # Thickness
            thick_val = opt["total_pavement_thickness"]
            thick_str = f"{thick_val:.0f} mm" if thick_val > 0 else "—"
            self.options_table.setItem(row_idx, 1, QTableWidgetItem(thick_str))

            # Layers
            self.options_table.setItem(row_idx, 2, QTableWidgetItem(opt["layers"]))

            # Approx Cost Index
            self.options_table.setItem(row_idx, 3, QTableWidgetItem(opt["estimated_cost_indicator"]))

            # Engineering Score
            score_val = opt["engineering_score"]
            score_str = str(score_val) if score_val > 0 else "N/A"
            self.options_table.setItem(row_idx, 4, QTableWidgetItem(score_str))

            # IITPAVE Status
            self.options_table.setItem(row_idx, 5, QTableWidgetItem(opt["iitpave_status"]))

            # Recommendation
            self.options_table.setItem(row_idx, 6, QTableWidgetItem(opt["recommendation_reason"]))

        # Select first option by default, or the previously selected design if persisted
        project = self.db.get_project(self._project_id)
        selected_opt_name = project.selected_design_option if project else None

        default_row = 0
        if selected_opt_name:
            for row_idx in range(len(options)):
                if options[row_idx]["option_name"] == selected_opt_name:
                    default_row = row_idx
                    break

        self.options_table.selectRow(default_row)
        self.btn_mark_selected.setEnabled(True)

        # Highlight recommendations and display smart recommendation box
        opt_d = next((o for o in options if o["design_type"] == "Recommended Option"), None)

        if opt_d and opt_d["total_pavement_thickness"] > 0:
            self.lbl_smart_rec.setText(
                f"<b>💡 Consultant Smart Recommendation:</b><br>{opt_d['recommendation_reason']}"
            )
            self.lbl_smart_rec.setVisible(True)
        else:
            self.lbl_smart_rec.setVisible(False)

    def _on_mark_selected(self) -> None:
        if self._project_id is None:
            return

        selected_ranges = self.options_table.selectedRanges()
        if not selected_ranges:
            QMessageBox.warning(self, "Warning", "Please select a design option from the table first.")
            return

        row_idx = selected_ranges[0].topRow()
        item = self.options_table.item(row_idx, 0)
        if not item:
            return

        option_name = item.text()
        try:
            self.db.update_selected_design_option(self._project_id, option_name)
            # Update workflow status for alternative selection stage
            self.db.update_module_status(self._project_id, "stabilized", "complete")
            self.saved.emit(self._project_id)
            QMessageBox.information(
                self,
                "Design Selection Persisted",
                f"Design Alternative <b>{option_name}</b> has been officially selected for this project."
            )
        except Exception as e:
            QMessageBox.critical(self, "Persist failed", str(e))

