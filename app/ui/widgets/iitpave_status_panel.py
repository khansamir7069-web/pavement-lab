"""IITPAVE Integration & Installation Manager UI Panel."""
from __future__ import annotations

import os
import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFormLayout,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QGridLayout,
)

from app.core import (
    IITPaveRunnerConfig,
    IITPAVE_RUNNER_STUB,
    IITPAVE_RUNNER_EXTERNAL,
    SUPPORTED_IITPAVE_RUNNER_MODES,
    load_persisted_config,
    save_persisted_config,
    detect_iitpave_version,
    get_last_run_info,
    validate_iitpave_environment,
    discover_iitpave_executable,
)
from app.core.iitpave.runner import default_iitpave_exe_path
from app.core.iitpave.workflow import (
    run_structural_iitpave_optimization_workflow,
    estimate_material_and_cost_increase,
)
from .common import Card, PageHeader, styled_button


def calculate_file_hash(filepath: Path | str) -> str:
    """Calculate the SHA256 checksum of a file for compliance logging."""
    path = Path(filepath)
    if not path.is_file():
        return "N/A"
    try:
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "Error Hashing"


class IITPaveWorkerThread(QThread):
    """Background worker thread to run IITPAVE verification silently without blocking the UI."""
    progress_updated = Signal(str)
    finished_successfully = Signal(object, list)  # (workflow_res, iterations)
    failed = Signal(str)

    def __init__(self, db, project_id: int, runner_config: IITPaveRunnerConfig, load=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = project_id
        self.runner_config = runner_config
        self.load = load
        self._is_cancelled = False

    def run(self) -> None:
        try:
            self.progress_updated.emit("Fetching latest structural design parameters...")
            sd = self.db.latest_structural_design(self.project_id)
            if not sd:
                self.failed.emit("No saved structural design found. Please perform and save a structural design first.")
                return

            # Reconstruct StructuralResult
            from app.core import StructuralInput, StructuralResult, PavementLayer

            inp_dict = json.loads(sd.inputs_json) if isinstance(sd.inputs_json, str) else sd.inputs_json
            comp_list = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json

            layers = []
            for ly in comp_list:
                layers.append(PavementLayer(
                    name=ly.get("name", ""),
                    thickness_mm=float(ly.get("thickness_mm", 0.0)),
                    material=ly.get("material", ""),
                    modulus_mpa=float(ly.get("modulus_mpa")) if ly.get("modulus_mpa") is not None else None,
                    poisson=float(ly.get("poisson")) if ly.get("poisson") is not None else None
                ))

            inputs = StructuralInput(
                road_category=inp_dict.get("road_category", "NH / SH"),
                design_life_years=int(inp_dict.get("design_life_years", 15)),
                initial_cvpd=float(inp_dict.get("initial_cvpd", 2000.0)),
                growth_rate_pct=float(inp_dict.get("growth_rate_pct", 7.5)),
                vdf=float(inp_dict.get("vdf", 2.5)),
                ldf=float(inp_dict.get("ldf", 0.75)),
                subgrade_cbr_pct=float(inp_dict.get("subgrade_cbr_pct", 5.0)),
                resilient_modulus_mpa=float(inp_dict.get("resilient_modulus_mpa")) if inp_dict.get("resilient_modulus_mpa") is not None else None,
                overrides=inp_dict.get("overrides", {})
            )

            result = StructuralResult(
                inputs=inputs,
                design_msa=float(sd.design_msa),
                growth_factor=float(sd.growth_factor),
                subgrade_mr_mpa=float(sd.subgrade_mr_mpa),
                composition=tuple(layers),
                total_pavement_thickness_mm=float(sd.total_pavement_thickness_mm),
                fatigue_check=sd.notes or "",
                rutting_check=sd.notes or "",
                notes=sd.notes or ""
            )

            self.progress_updated.emit("Initiating IITPAVE validation and auto-optimization loop...")

            def log_callback(msg: str):
                if self._is_cancelled:
                    raise InterruptedError("Cancellation requested by the user.")
                self.progress_updated.emit(msg)

            # Trigger optimization loop
            wf_res, iterations = run_structural_iitpave_optimization_workflow(
                result,
                db=self.db,
                project_id=self.project_id,
                runner_config=self.runner_config,
                load=self.load,
                log_callback=log_callback
            )

            if self._is_cancelled:
                self.failed.emit("Cancellation requested by the user.")
                return

            self.finished_successfully.emit(wf_res, iterations)
        except InterruptedError:
            self.failed.emit("Analysis cancelled.")
        except Exception as e:
            self.failed.emit(f"Subprocess run failed: {str(e)}")

    def cancel(self) -> None:
        self._is_cancelled = True


class IITPaveStatusPanel(QWidget):
    """Panel for configuring, validating, running, and visualizing IITPAVE verification runs."""
    
    config_updated = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id = None
        self._project_name = ""
        self._worker_thread = None
        self._build()
        self.refresh()

    def set_project(self, project_id: int | None, name: str = "") -> None:
        self._project_id = project_id
        self._project_name = name
        self.btn_run_verification.setEnabled(project_id is not None)
        
        if project_id:
            self.lbl_project_banner.setText(f"Project Active: <b>{name}</b> (ID: {project_id})")
            self.lbl_project_banner.setStyleSheet("color:#1f3a68; font-weight:bold;")
        else:
            self.lbl_project_banner.setText("No project loaded. Load or setup a project first.")
            self.lbl_project_banner.setStyleSheet("color:#a81f1f; font-weight:bold;")
            
        self.refresh()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "External IITPAVE Verification (Optional)",
            "Perform validation and parity checks against separately installed external IITPAVE software."
        )
        lay.addWidget(self.header)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # Tab 1: Execution & Verification
        tab_exec = QWidget()
        elay = QVBoxLayout(tab_exec)
        elay.setContentsMargins(20, 16, 20, 16)
        elay.setSpacing(14)

        # Project Info Banner
        self.lbl_project_banner = QLabel("No project loaded.")
        elay.addWidget(self.lbl_project_banner)

        self.lbl_optional_validation_note = QLabel(
            "⚠️ <b>Note:</b> This page is exclusively for performing optional validation/parity comparisons "
            "against a separately installed, external IITPAVE executable. It is not the main pavement design engine."
        )
        self.lbl_optional_validation_note.setStyleSheet(
            "background-color: #fcf3cf; color: #7e5109; border: 1px solid #f9e79f; "
            "border-radius: 4px; padding: 10px 14px; font-size: 10pt;"
        )
        self.lbl_optional_validation_note.setWordWrap(True)
        elay.addWidget(self.lbl_optional_validation_note)

        # Verification controls
        ctrl_card = Card()
        cl = QHBoxLayout(ctrl_card)
        self.btn_run_verification = styled_button("Run Mechanistic Verification", "primary")
        self.btn_run_verification.clicked.connect(self._on_run_verification)
        self.btn_cancel_verification = styled_button("Cancel", "secondary")
        self.btn_cancel_verification.setEnabled(False)
        self.btn_cancel_verification.clicked.connect(self._on_cancel_verification)
        
        cl.addWidget(self.btn_run_verification)
        cl.addWidget(self.btn_cancel_verification)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        cl.addWidget(self.progress_bar)
        
        cl.addStretch()
        elay.addWidget(ctrl_card)

        # Dynamic Status Cards
        self.card_verdict = Card()
        vl = QVBoxLayout(self.card_verdict)
        self.lbl_overall_verdict = QLabel("<b>Overall Verdict: N/A</b>")
        self.lbl_overall_verdict.setAlignment(Qt.AlignCenter)
        self.lbl_overall_verdict.setStyleSheet("font-size: 14pt; padding: 10px; border-radius: 4px; background:#f5f6f8; color:#333;")
        vl.addWidget(self.lbl_overall_verdict)
        
        grid_results = QGridLayout()
        # Fatigue details
        self.lbl_fatigue_strain = QLabel("Tensile Strain (εt): —")
        self.lbl_fatigue_life = QLabel("Fatigue Life (Nf): —")
        self.lbl_fatigue_status = QLabel("Fatigue Check: —")
        grid_results.addWidget(self.lbl_fatigue_strain, 0, 0)
        grid_results.addWidget(self.lbl_fatigue_life, 0, 1)
        grid_results.addWidget(self.lbl_fatigue_status, 0, 2)
        
        # Rutting details
        self.lbl_rutting_strain = QLabel("Compressive Strain (εv): —")
        self.lbl_rutting_life = QLabel("Rutting Life (Nr): —")
        self.lbl_rutting_status = QLabel("Rutting Check: —")
        grid_results.addWidget(self.lbl_rutting_strain, 1, 0)
        grid_results.addWidget(self.lbl_rutting_life, 1, 1)
        grid_results.addWidget(self.lbl_rutting_status, 1, 2)
        
        vl.addLayout(grid_results)
        elay.addWidget(self.card_verdict)

        # Recommendation Card
        self.card_recommend = Card()
        rl = QVBoxLayout(self.card_recommend)
        rl.addWidget(QLabel("<b>Engineering Recommendation</b>"))
        self.lbl_recommend_action = QLabel("Recommended Action: —")
        self.lbl_recommend_reason = QLabel("Reason: —")
        self.lbl_recommend_improvement = QLabel("Expected Improvement: —")
        self.lbl_recommend_materials = QLabel("Estimated Additional Materials: —")
        self.lbl_recommend_cost = QLabel("Expected Cost Impact: —")
        
        rl.addWidget(self.lbl_recommend_action)
        rl.addWidget(self.lbl_recommend_reason)
        rl.addWidget(self.lbl_recommend_improvement)
        rl.addWidget(self.lbl_recommend_materials)
        rl.addWidget(self.lbl_recommend_cost)
        elay.addWidget(self.card_recommend)

        # Iterations History Table
        tbl_card = Card()
        tl = QVBoxLayout(tbl_card)
        tl.addWidget(QLabel("<b>Iterative Optimization History</b>"))
        
        self.tbl_iterations = QTableWidget()
        self.tbl_iterations.setColumnCount(11)
        self.tbl_iterations.setHorizontalHeaderLabels([
            "Attempt", "BC (mm)", "DBM (mm)", "WMM (mm)", "GSB (mm)",
            "Max εt", "Max εv", "Fatigue", "Rutting", "Decision", "Engineering Reason"
        ])
        self.tbl_iterations.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_iterations.horizontalHeader().setStretchLastSection(True)
        self.tbl_iterations.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_iterations.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_iterations.setFixedHeight(180)
        tl.addWidget(self.tbl_iterations)
        elay.addWidget(tbl_card)

        # Live log viewer
        log_view_card = Card()
        lvl = QVBoxLayout(log_view_card)
        lvl.addWidget(QLabel("<b>Execution & Traceability Logs</b>"))
        self.txt_live_logs = QTextEdit()
        self.txt_live_logs.setReadOnly(True)
        self.txt_live_logs.setFontFamily("Consolas")
        self.txt_live_logs.setFontPointSize(9)
        self.txt_live_logs.setFixedHeight(120)
        lvl.addWidget(self.txt_live_logs)
        elay.addWidget(log_view_card)

        scroll_exec = QScrollArea()
        scroll_exec.setWidgetResizable(True)
        scroll_exec.setWidget(tab_exec)
        self.tabs.addTab(scroll_exec, "Verification & Results")

        # Tab 2: Settings & Integration Setup
        tab_settings = QWidget()
        slay = QVBoxLayout(tab_settings)
        slay.setContentsMargins(20, 16, 20, 16)
        slay.setSpacing(14)

        # 1. Separately Licensed Dependency Notice
        notice_card = Card()
        nl = QVBoxLayout(notice_card)
        lbl_notice = QLabel(
            "⚠️ <b>Separately Licensed Dependency Notice:</b> RoadX Professional Suite integrates with a separately "
            "licensed IITPAVE installation. The official mechanistic calculation engine is not bundled, distributed, "
            "or licensed with this package. The user must configure and license their own <code>IITPAVE.exe</code> "
            "executable path separately."
        )
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet("color: #7d6608; background-color: #fef9e7; border: 1px solid #fcf3cf; padding: 10px; border-radius: 4px;")
        nl.addWidget(lbl_notice)
        slay.addWidget(notice_card)

        # 2. Integration status & path
        path_card = Card()
        pl = QVBoxLayout(path_card)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.addWidget(QLabel("<b>IITPAVE.exe Installation Discovery & Validation</b>"))
        
        self.lbl_engine_status = QLabel("")
        self.lbl_engine_status.setMinimumHeight(32)
        pl.addWidget(self.lbl_engine_status)

        # Diagnostics fields
        diag_layout = QFormLayout()
        self.lbl_diag_path = QLabel("—")
        self.lbl_diag_version = QLabel("—")
        self.lbl_diag_sha = QLabel("—")
        self.lbl_diag_test = QLabel("—")
        diag_layout.addRow("Active Executable Path:", self.lbl_diag_path)
        diag_layout.addRow("Detected Version:", self.lbl_diag_version)
        diag_layout.addRow("SHA256 Checksum:", self.lbl_diag_sha)
        diag_layout.addRow("Diagnostics Run Status:", self.lbl_diag_test)
        pl.addLayout(diag_layout)
        pl.addSpacing(10)
        
        form_path = QFormLayout()
        self.cb_candidates = QComboBox()
        self.cb_candidates.currentIndexChanged.connect(self._on_candidate_changed)
        form_path.addRow("Discovered Binaries", self.cb_candidates)
        
        manual_row = QHBoxLayout()
        self.txt_manual_path = QLineEdit()
        self.txt_manual_path.setPlaceholderText("Select or enter custom path to IITPAVE.exe...")
        btn_browse = styled_button("Browse...", "secondary")
        btn_browse.clicked.connect(self._on_browse)
        manual_row.addWidget(self.txt_manual_path)
        manual_row.addWidget(btn_browse)
        form_path.addRow("Custom Executable Path", manual_row)
        
        pl.addLayout(form_path)
        
        btn_validate_row = QHBoxLayout()
        btn_validate = styled_button("Validate Selected Executable", "secondary")
        btn_validate.clicked.connect(self._on_validate)
        btn_validate_row.addWidget(btn_validate)
        btn_validate_row.addStretch()
        pl.addLayout(btn_validate_row)
        slay.addWidget(path_card)

        # Configurable engineering limits
        limits_card = Card()
        llay = QVBoxLayout(limits_card)
        llay.addWidget(QLabel("<b>Configurable Engineering Limits (IRC:37 Constants)</b>"))
        
        form_limits = QFormLayout()
        self.spin_bc_min = QSpinBox()
        self.spin_bc_min.setRange(20, 100)
        self.spin_bc_min.setValue(30)
        self.spin_bc_min.setSuffix(" mm")
        
        self.spin_bc_max = QSpinBox()
        self.spin_bc_max.setRange(50, 150)
        self.spin_bc_max.setValue(80)
        self.spin_bc_max.setSuffix(" mm")
        
        form_limits.addRow("BC Min Thickness", self.spin_bc_min)
        form_limits.addRow("BC Max Thickness", self.spin_bc_max)
        
        self.spin_dbm_min = QSpinBox()
        self.spin_dbm_min.setRange(40, 150)
        self.spin_dbm_min.setValue(50)
        self.spin_dbm_min.setSuffix(" mm")
        
        self.spin_dbm_max = QSpinBox()
        self.spin_dbm_max.setRange(150, 400)
        self.spin_dbm_max.setValue(300)
        self.spin_dbm_max.setSuffix(" mm")
        
        form_limits.addRow("DBM Min Thickness", self.spin_dbm_min)
        form_limits.addRow("DBM Max Thickness", self.spin_dbm_max)
        
        self.spin_wmm_max = QSpinBox()
        self.spin_wmm_max.setRange(100, 300)
        self.spin_wmm_max.setValue(250)
        self.spin_wmm_max.setSuffix(" mm")
        
        self.spin_gsb_max = QSpinBox()
        self.spin_gsb_max.setRange(200, 600)
        self.spin_gsb_max.setValue(400)
        self.spin_gsb_max.setSuffix(" mm")
        
        form_limits.addRow("WMM Max Thickness limit", self.spin_wmm_max)
        form_limits.addRow("GSB Max Thickness limit", self.spin_gsb_max)
        
        self.spin_iterations = QSpinBox()
        self.spin_iterations.setRange(5, 50)
        self.spin_iterations.setValue(15)
        self.spin_iterations.setSuffix(" iterations")
        form_limits.addRow("Max Optimization Steps", self.spin_iterations)
        
        llay.addLayout(form_limits)
        slay.addWidget(limits_card)

        # Save settings
        cfg_card = Card()
        ccl = QVBoxLayout(cfg_card)
        ccl.addWidget(QLabel("<b>Process & Runtime Settings</b>"))
        
        form_cfg = QFormLayout()
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Production Mode (External Executable)", "IRC Catalogue Design (Decision Support Mode)"])
        form_cfg.addRow("Execution Mode", self.cb_mode)
        
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(5.0, 300.0)
        self.spin_timeout.setValue(60.0)
        self.spin_timeout.setSuffix(" seconds")
        form_cfg.addRow("Process Timeout", self.spin_timeout)
        
        self.chk_path_search = QCheckBox("Scan System PATH folder for IITPAVE binary")
        form_cfg.addRow("PATH Discovery", self.chk_path_search)
        ccl.addLayout(form_cfg)
        
        btn_save_row = QHBoxLayout()
        btn_save = styled_button("Save Integration Settings", "primary")
        btn_save.clicked.connect(self._on_save_settings)
        btn_save_row.addWidget(btn_save)
        btn_save_row.addStretch()
        ccl.addLayout(btn_save_row)
        slay.addWidget(cfg_card)

        # 3. Help & Setup Guide
        help_card = Card()
        hl = QVBoxLayout(help_card)
        hl.addWidget(QLabel("<b>IITPAVE Setup & Configuration Guide</b>"))
        lbl_help = QLabel(
            "1. Obtain a licensed copy of <code>IITPAVE.exe</code> from the Indian Roads Congress or your institution.<br/>"
            "2. Save the executable locally on your system (e.g., <code>C:\\IITPAVE\\IITPAVE.exe</code>).<br/>"
            "3. Select <b>Custom Manual Selection...</b> from the candidates list or click <b>Browse...</b> to link the file.<br/>"
            "4. Alternatively, define the environment variable <code>ROADX_IITPAVE_EXE</code> to point to your binary.<br/>"
            "5. Click <b>Save Integration Settings</b> to commit the configuration path."
        )
        lbl_help.setWordWrap(True)
        lbl_help.setStyleSheet("color: #565d6d; font-size: 9.5pt; line-height: 1.4;")
        hl.addWidget(lbl_help)
        slay.addWidget(help_card)

        scroll_settings = QScrollArea()
        scroll_settings.setWidgetResizable(True)
        scroll_settings.setWidget(tab_settings)
        self.tabs.addTab(scroll_settings, "Integration Settings")

    def refresh(self) -> None:
        """Reload configurations and update display widgets."""
        cfg = load_persisted_config()
        
        # Populate settings fields
        mode_idx = 0 if cfg.mode == IITPAVE_RUNNER_EXTERNAL else 1
        self.cb_mode.setCurrentIndex(mode_idx)
        self.spin_timeout.setValue(cfg.timeout_sec)
        self.chk_path_search.setChecked(cfg.include_path_search)
        
        # Engineering limits
        self.spin_bc_min.setValue(int(cfg.bc_min))
        self.spin_bc_max.setValue(int(cfg.bc_max))
        self.spin_dbm_min.setValue(int(cfg.dbm_min))
        self.spin_dbm_max.setValue(int(cfg.dbm_max))
        self.spin_wmm_max.setValue(int(cfg.wmm_max))
        self.spin_gsb_max.setValue(int(cfg.gsb_max))
        self.spin_iterations.setValue(cfg.max_iterations)
        
        # Validate executable path candidates
        validation = validate_iitpave_environment(
            configured_path=cfg.configured_executable_path or None,
            include_path_search=cfg.include_path_search,
        )
        
        self.cb_candidates.blockSignals(True)
        self.cb_candidates.clear()
        for c in validation.candidates:
            source_lbl = f"{c.source.upper()}: {c.path}"
            if not c.exists:
                source_lbl += " (Not Found)"
            elif not c.is_file:
                source_lbl += " (Directory/Invalid)"
            self.cb_candidates.addItem(source_lbl, str(c.path))
            
        self.cb_candidates.addItem("Custom Manual Selection...", "")
        
        if validation.selected_path:
            idx = self.cb_candidates.findData(str(validation.selected_path))
            if idx >= 0:
                self.cb_candidates.setCurrentIndex(idx)
                self.txt_manual_path.setText(str(validation.selected_path))
        else:
            self.cb_candidates.setCurrentIndex(self.cb_candidates.count() - 1)
            self.txt_manual_path.setText(cfg.configured_executable_path)
        self.cb_candidates.blockSignals(False)

        # Update detection badges and diagnostics
        if validation.selected_path:
            self.lbl_engine_status.setText("🟢 IITPAVE CONNECTED — Ready for silent subprocess validation runs.")
            self.lbl_engine_status.setStyleSheet("color:#196f3d; font-weight:bold;")
            self.lbl_diag_path.setText(str(validation.selected_path))
            self.lbl_diag_path.setStyleSheet("color:#196f3d;")
            ver = detect_iitpave_version(validation.selected_path) or "Unknown"
            self.lbl_diag_version.setText(ver)
            sha = calculate_file_hash(validation.selected_path)
            self.lbl_diag_sha.setText(sha)
            self.lbl_diag_sha.setStyleSheet("font-family: Consolas; font-size: 9pt;")
            
            # Simple status verification
            self.lbl_diag_test.setText("Ready (A diagnostic test run can be performed during project verification)")
            self.lbl_diag_test.setStyleSheet("color:#333;")
        else:
            self.lbl_engine_status.setText("🟡 IITPAVE NOT CONNECTED — Runs will fall back or be blocked.")
            self.lbl_engine_status.setStyleSheet("color:#a67c00; font-weight:bold;")
            self.lbl_diag_path.setText("Not Connected (Separate external license required)")
            self.lbl_diag_path.setStyleSheet("color:#a81f1f;")
            self.lbl_diag_version.setText("Unavailable")
            self.lbl_diag_sha.setText("Unavailable")
            self.lbl_diag_test.setText("Unavailable")
            self.lbl_diag_test.setStyleSheet("color:#a81f1f;")

        # Populate last run details if available from the database
        if self._project_id:
            last_mv = self.db.latest_mechanistic_validation(self._project_id)
            if last_mv:
                self._render_results(last_mv)

    def _render_results(self, mv) -> None:
        """Render results from a saved database MechanisticValidation record."""
        # Overall Safe banner
        if mv.refused or mv.is_placeholder:
            self.lbl_overall_verdict.setText("<b>Overall Verdict: Not Executed / Unavailable</b>")
            self.lbl_overall_verdict.setStyleSheet("font-size: 14pt; padding: 10px; border-radius: 4px; background:#f5f6f8; color:#666;")
        elif mv.fatigue_verdict == "PASS" and mv.rutting_verdict == "PASS":
            self.lbl_overall_verdict.setText("<b>Overall Verdict: DESIGN SAFE (MECH. COMPLIANT)</b>")
            self.lbl_overall_verdict.setStyleSheet("font-size: 14pt; padding: 10px; border-radius: 4px; background:#d4efdf; color:#196f3d;")
        else:
            self.lbl_overall_verdict.setText("<b>Overall Verdict: DESIGN UNSAFE / FAILED</b>")
            self.lbl_overall_verdict.setStyleSheet("font-size: 14pt; padding: 10px; border-radius: 4px; background:#f9d5d5; color:#a81f1f;")

        # Load values
        summary_dict = {}
        if mv.summary_json:
            try:
                summary_dict = json.loads(mv.summary_json) if isinstance(mv.summary_json, str) else mv.summary_json
            except Exception:
                pass

        fatigue_strain = summary_dict.get("fatigue", {}).get("epsilon_t_microstrain")
        rutting_strain = summary_dict.get("rutting", {}).get("epsilon_v_microstrain")

        self.lbl_fatigue_strain.setText(f"Tensile Strain (εt): <b>{fatigue_strain:.2f}</b> microstrain" if fatigue_strain is not None else "Tensile Strain (εt): —")
        self.lbl_fatigue_life.setText(f"Fatigue Life (Nf): <b>{mv.fatigue_life_msa:.2f}</b> MSA" if mv.fatigue_life_msa is not None else "Fatigue Life (Nf): —")
        self.lbl_fatigue_status.setText(f"Fatigue Check: <b>{mv.fatigue_verdict or 'N/A'}</b>")
        
        self.lbl_rutting_strain.setText(f"Compressive Strain (εv): <b>{rutting_strain:.2f}</b> microstrain" if rutting_strain is not None else "Compressive Strain (εv): —")
        self.lbl_rutting_life.setText(f"Rutting Life (Nr): <b>{mv.rutting_life_msa:.2f}</b> MSA" if mv.rutting_life_msa is not None else "Rutting Life (Nr): —")
        self.lbl_rutting_status.setText(f"Rutting Check: <b>{mv.rutting_verdict or 'N/A'}</b>")

        # Load Iterations history
        iter_list = []
        if mv.iteration_history_json:
            try:
                iter_list = json.loads(mv.iteration_history_json) if isinstance(mv.iteration_history_json, str) else mv.iteration_history_json
            except Exception:
                pass

        self.tbl_iterations.setRowCount(len(iter_list))
        for row_idx, step in enumerate(iter_list):
            thicknesses = step.get("thicknesses", {})
            self.tbl_iterations.setItem(row_idx, 0, QTableWidgetItem(str(step.get("attempt"))))
            self.tbl_iterations.setItem(row_idx, 1, QTableWidgetItem(f"{thicknesses.get('BC', 0.0):.0f}"))
            self.tbl_iterations.setItem(row_idx, 2, QTableWidgetItem(f"{thicknesses.get('DBM', 0.0):.0f}"))
            self.tbl_iterations.setItem(row_idx, 3, QTableWidgetItem(f"{thicknesses.get('WMM', 0.0):.0f}"))
            self.tbl_iterations.setItem(row_idx, 4, QTableWidgetItem(f"{thicknesses.get('GSB', 0.0):.0f}"))
            self.tbl_iterations.setItem(row_idx, 5, QTableWidgetItem(f"{step.get('epsilon_t', 0.0):.2f}"))
            self.tbl_iterations.setItem(row_idx, 6, QTableWidgetItem(f"{step.get('epsilon_v', 0.0):.2f}"))
            self.tbl_iterations.setItem(row_idx, 7, QTableWidgetItem(str(step.get("fatigue_verdict"))))
            self.tbl_iterations.setItem(row_idx, 8, QTableWidgetItem(str(step.get("rutting_verdict"))))
            self.tbl_iterations.setItem(row_idx, 9, QTableWidgetItem(str(step.get("decision"))))
            self.tbl_iterations.setItem(row_idx, 10, QTableWidgetItem(str(step.get("reason"))))

        # Recommendations display
        if iter_list:
            last_step = iter_list[-1]
            if last_step.get("verdict") == "PASS":
                self.lbl_recommend_action.setText("Recommended Action: <b>Design is Verified SAFE</b>")
                self.lbl_recommend_reason.setText(f"Reason: Thickness optimization resolved compliance errors in attempt {last_step.get('attempt')}.")
            else:
                self.lbl_recommend_action.setText("Recommended Action: <b>Manual Redesign Required</b>")
                self.lbl_recommend_reason.setText("Reason: Optimization reached iteration limit without resolving safety factors.")
                
            # Aggregate improvements
            first_step = iter_list[0]
            imp_f = 0.0
            imp_r = 0.0
            if first_step.get("nf", 0.0) > 0.0:
                imp_f = ((last_step.get("nf", 0.0) - first_step.get("nf", 0.0)) / first_step.get("nf", 0.0)) * 100.0
            if first_step.get("nr", 0.0) > 0.0:
                imp_r = ((last_step.get("nr", 0.0) - first_step.get("nr", 0.0)) / first_step.get("nr", 0.0)) * 100.0
                
            self.lbl_recommend_improvement.setText(f"Expected Improvement: <b>Fatigue Life +{imp_f:.1f}%</b> | <b>Rutting Life +{imp_r:.1f}%</b>")
            
            # Additional material and cost
            tot_tonnage = sum(step.get("estimated_additional_tonnage", 0.0) for step in iter_list)
            tot_cost = sum(step.get("estimated_cost_increase", 0.0) for step in iter_list)
            self.lbl_recommend_materials.setText(f"Estimated Additional Materials: <b>{tot_tonnage:.2f} Tons</b>")
            self.lbl_recommend_cost.setText(f"Expected Cost Impact: <b>Rs. {tot_cost:,.2f}</b>")
        else:
            self.lbl_recommend_action.setText("Recommended Action: —")
            self.lbl_recommend_reason.setText("Reason: —")
            self.lbl_recommend_improvement.setText("Expected Improvement: —")
            self.lbl_recommend_materials.setText("Estimated Additional Materials: —")
            self.lbl_recommend_cost.setText("Expected Cost Impact: —")

        # Load logs
        self.txt_live_logs.clear()
        if mv.stdout_log:
            self.txt_live_logs.append("----- SUBPROCESS STDOUT LOG -----")
            self.txt_live_logs.append(mv.stdout_log)
        if mv.stderr_log:
            self.txt_live_logs.append("\n----- SUBPROCESS STDERR LOG -----")
            self.txt_live_logs.append(mv.stderr_log)

    def _on_candidate_changed(self, idx: int) -> None:
        if idx < 0:
            return
        path = self.cb_candidates.currentData()
        if path:
            self.txt_manual_path.setText(path)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select IITPAVE Executable", "", "Executables (IITPAVE.exe iitpave)"
        )
        if path:
            self.txt_manual_path.setText(path)
            self.cb_candidates.setCurrentIndex(self.cb_candidates.count() - 1)

    def _on_validate(self) -> None:
        path_str = self.txt_manual_path.text().strip()
        if not path_str:
            QMessageBox.warning(self, "Validation", "Please select or input an executable path first.")
            return
            
        path = Path(path_str)
        if not path.is_file():
            QMessageBox.critical(self, "Validation Failed", f"The specified path is not a file: {path_str}")
            return
            
        version = detect_iitpave_version(path)
        file_hash = calculate_file_hash(path)
        
        # Run dry run!
        from app.core import select_iitpave_runner, check_iitpave_dry_run_readiness, IITPaveRunnerConfig
        cfg = IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=path_str
        )
        selection = select_iitpave_runner(cfg)
        dry_run = check_iitpave_dry_run_readiness(selection)
        
        if dry_run.ok:
            status_text = f"Ready (Diagnostics successful, code {dry_run.returncode})"
            QMessageBox.information(
                self,
                "Validation Successful",
                f"The executable is valid and runnable!\n\n"
                f"Detected Version: {version}\n"
                f"SHA256 Checksum: {file_hash}\n"
                f"Return Code: {dry_run.returncode}"
            )
        else:
            status_text = f"Failed: {dry_run.blocked_reason or 'Verification failed'}"
            QMessageBox.warning(
                self,
                "Validation Warning",
                f"The executable exists but dry-run verification failed/warned:\n\n"
                f"Reason: {dry_run.blocked_reason}\n"
                f"Detected Version: {version}\n"
                f"SHA256 Checksum: {file_hash}"
            )
        
        # Update diagnostics display fields
        self.lbl_diag_path.setText(path_str)
        self.lbl_diag_version.setText(version)
        self.lbl_diag_sha.setText(file_hash)
        self.lbl_diag_test.setText(status_text)

    def _on_save_settings(self) -> None:
        path_str = self.txt_manual_path.text().strip()
        mode_str = IITPAVE_RUNNER_EXTERNAL if self.cb_mode.currentIndex() == 0 else IITPAVE_RUNNER_STUB
        
        cfg = IITPaveRunnerConfig(
            mode=mode_str,
            configured_executable_path=path_str,
            include_path_search=self.chk_path_search.isChecked(),
            timeout_sec=self.spin_timeout.value(),
            bc_min=float(self.spin_bc_min.value()),
            bc_max=float(self.spin_bc_max.value()),
            dbm_min=float(self.spin_dbm_min.value()),
            dbm_max=float(self.spin_dbm_max.value()),
            wmm_max=float(self.spin_wmm_max.value()),
            gsb_max=float(self.spin_gsb_max.value()),
            max_iterations=self.spin_iterations.value(),
        )
        
        try:
            save_persisted_config(cfg)
            QMessageBox.information(self, "Settings Saved", "IITPAVE Integration settings saved successfully.")
            self.config_updated.emit()
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Failed to persist configuration settings: {e}")

    def _on_run_verification(self) -> None:
        """Run verification in background thread."""
        if not self._project_id:
            QMessageBox.warning(self, "Verification", "Please load a project first.")
            return

        cfg = load_persisted_config()
        if cfg.mode == IITPAVE_RUNNER_EXTERNAL:
            validation = validate_iitpave_environment(
                configured_path=cfg.configured_executable_path or None,
                include_path_search=cfg.include_path_search,
            )
            if not validation.selected_path:
                QMessageBox.warning(
                    self,
                    "IITPAVE Not Configured",
                    "Licensed IITPAVE executable is not configured.\n\n"
                    "Browse and select IITPAVE.exe to run mechanistic verification."
                )
                return

        self.txt_live_logs.clear()
        self.progress_bar.setVisible(True)
        self.btn_run_verification.setEnabled(False)
        self.btn_cancel_verification.setEnabled(True)

        self._worker_thread = IITPaveWorkerThread(
            db=self.db,
            project_id=self._project_id,
            runner_config=cfg
        )
        self._worker_thread.progress_updated.connect(self._on_worker_progress)
        self._worker_thread.finished_successfully.connect(self._on_worker_success)
        self._worker_thread.failed.connect(self._on_worker_failed)
        
        self._worker_thread.start()

    def _on_cancel_verification(self) -> None:
        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.cancel()
            self._on_worker_progress("Stopping subprocess execution gracefully...")

    def _on_worker_progress(self, msg: str) -> None:
        self.txt_live_logs.append(msg)

    def _on_worker_success(self, wf_res: Any, iterations: list[dict[str, Any]]) -> None:
        self._cleanup_worker()
        
        try:
            # 1. Update project sync version and save structural design
            self.db.save_structural_design(project_id=self._project_id, result=wf_res.structural_result)

            # Calculate executable details
            exe_path_str = str(wf_res.selection.selected_path) if wf_res.selection and wf_res.selection.selected_path else "stub"
            exe_hash_val = calculate_file_hash(exe_path_str) if exe_path_str != "stub" else "N/A"
            exe_ver_val = detect_iitpave_version(exe_path_str) if exe_path_str != "stub" else "Stub V1"
            
            # Map paths
            run_dir = ""
            inp_path = ""
            out_path = ""
            if wf_res.selection and wf_res.selection.selected_path:
                run_dir = str(wf_res.selection.config.working_dir)
                inp_path = str(Path(run_dir) / wf_res.selection.config.input_filename) if run_dir else ""
                out_path = str(Path(run_dir) / wf_res.selection.config.output_filename) if run_dir else ""
                
            # 2. Save mechanistic validation summary with metadata
            self.db.save_mechanistic_validation(
                project_id=self._project_id,
                summary=wf_res.summary,
                inputs=wf_res.as_dict(),
                exe_path=exe_path_str,
                input_filepath=inp_path,
                output_filepath=out_path,
                stdout_log=wf_res.output_text,
                stderr_log=wf_res.blocked_reason or "",
                iteration_history_json=json.dumps(iterations),
                recommended_thickness_json=json.dumps({ly.name: ly.thickness_mm for ly in wf_res.structural_result.composition})
            )
            
            # Log audit action
            self.db.log_project_audit(
                project_id=self._project_id,
                module="iitpave_status",
                action="Verification Run Complete",
                detail=f"Iterations: {len(iterations)}, Overall Status: {'SAFE' if wf_res.ok else 'UNSAFE'}"
            )

            # Increment synchronization model state
            self.db.mark_module_synced(self._project_id, "structural", ["traffic", "subgrade"])

            # Refresh Status bar widget
            self.config_updated.emit()
            self.refresh()
            
            QMessageBox.information(self, "Verification Complete", "Pavement verification run succeeded and results persisted.")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save validation results: {e}")

    def _on_worker_failed(self, err_msg: str) -> None:
        self._cleanup_worker()
        QMessageBox.critical(self, "Verification Failed", f"Subprocess run failed:\n\n{err_msg}")
        self.txt_live_logs.append(f"\n[FATAL ERROR] {err_msg}")

    def _cleanup_worker(self) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run_verification.setEnabled(True)
        self.btn_cancel_verification.setEnabled(False)
        self._worker_thread = None
