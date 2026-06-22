"""IITPAVE Integration & Installation Manager UI Panel."""
from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QCheckBox,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFormLayout,
    QScrollArea,
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
from .common import Card, PageHeader, styled_button

class IITPaveStatusPanel(QWidget):
    """Panel for configuring and validating the local IITPAVE executable integration."""
    
    config_updated = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build()
        self.refresh()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "IITPAVE Integration Manager",
            "Configure, discover, and validate the local IITPAVE executable for mechanistic pavement verification."
        )
        lay.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(14)

        # 1. Integration Status Card
        status_card = Card()
        sl = QVBoxLayout(status_card)
        sl.setContentsMargins(20, 16, 20, 16)
        sl.addWidget(QLabel("<b>Integration & Verification Status</b>"))
        
        status_row = QHBoxLayout()
        self.lbl_detection_badge = QLabel("Not Detected")
        self.lbl_detection_badge.setAlignment(Qt.AlignCenter)
        self.lbl_detection_badge.setFixedSize(140, 24)
        
        self.lbl_mode_badge = QLabel("Decision Support Mode")
        self.lbl_mode_badge.setAlignment(Qt.AlignCenter)
        self.lbl_mode_badge.setFixedSize(160, 24)
        
        status_row.addWidget(self.lbl_detection_badge)
        status_row.addWidget(self.lbl_mode_badge)
        status_row.addStretch()
        sl.addLayout(status_row)
        
        self.lbl_selected_path = QLabel("Active Executable: —")
        self.lbl_selected_path.setStyleSheet("color:#6a7180; font-size:10pt;")
        self.lbl_selected_path.setWordWrap(True)
        sl.addWidget(self.lbl_selected_path)
        
        self.lbl_detected_version = QLabel("Detected Version Info: —")
        self.lbl_detected_version.setStyleSheet("color:#1f3a68; font-size:10pt; font-weight:bold;")
        self.lbl_detected_version.setWordWrap(True)
        sl.addWidget(self.lbl_detected_version)
        
        bl.addWidget(status_card)

        # 2. Path Selection Card
        path_card = Card()
        pl = QVBoxLayout(path_card)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.addWidget(QLabel("<b>IITPAVE.exe Installation & Discovery</b>"))
        
        form_path = QFormLayout()
        
        # Candidate dropdown
        self.cb_candidates = QComboBox()
        self.cb_candidates.currentIndexChanged.connect(self._on_candidate_changed)
        form_path.addRow("Discovered Binaries", self.cb_candidates)
        
        # Manual input
        manual_row = QHBoxLayout()
        self.txt_manual_path = QLineEdit()
        self.txt_manual_path.setPlaceholderText("Select or enter a custom path to IITPAVE.exe...")
        btn_browse = styled_button("Browse...", "secondary")
        btn_browse.clicked.connect(self._on_browse)
        manual_row.addWidget(self.txt_manual_path)
        manual_row.addWidget(btn_browse)
        form_path.addRow("Custom Executable Path", manual_row)
        
        pl.addLayout(form_path)
        
        btn_validate_row = QHBoxLayout()
        btn_validate = styled_button("Validate Selected Executable", "primary")
        btn_validate.clicked.connect(self._on_validate)
        btn_validate_row.addWidget(btn_validate)
        btn_validate_row.addStretch()
        pl.addLayout(btn_validate_row)
        
        bl.addWidget(path_card)

        # 3. Persistence & Configuration Card
        config_card = Card()
        cl = QVBoxLayout(config_card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.addWidget(QLabel("<b>Runner Settings</b>"))
        
        form_cfg = QFormLayout()
        
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Production Mode (External Executable)", "Decision Support Mode (Stub/Placeholder)"])
        form_cfg.addRow("Execution Mode", self.cb_mode)
        
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(5.0, 300.0)
        self.spin_timeout.setValue(60.0)
        self.spin_timeout.setSuffix(" seconds")
        form_cfg.addRow("Process Timeout", self.spin_timeout)
        
        self.chk_path_search = QCheckBox("Scan System PATH folder for IITPAVE binary")
        form_cfg.addRow("PATH Discovery", self.chk_path_search)
        
        cl.addLayout(form_cfg)
        
        btn_save_row = QHBoxLayout()
        btn_save = styled_button("Save Integration Settings", "primary")
        btn_save.clicked.connect(self._on_save_settings)
        btn_save_row.addWidget(btn_save)
        btn_save_row.addStretch()
        cl.addLayout(btn_save_row)
        
        bl.addWidget(config_card)

        # 4. Last Run Log Card
        log_card = Card()
        ll = QVBoxLayout(log_card)
        ll.setContentsMargins(20, 16, 20, 16)
        ll.addWidget(QLabel("<b>Last Subprocess Run Logs</b>"))
        
        self.lbl_log_meta = QLabel("No execution logged recently.")
        self.lbl_log_meta.setStyleSheet("color:#6a7180; font-size:10pt;")
        ll.addWidget(self.lbl_log_meta)
        
        ll.addWidget(QLabel("Generated Input File (iitp_inp.dat):"))
        self.txt_inp_log = QTextEdit()
        self.txt_inp_log.setReadOnly(True)
        self.txt_inp_log.setFixedHeight(120)
        self.txt_inp_log.setFontFamily("Consolas")
        self.txt_inp_log.setFontPointSize(9)
        ll.addWidget(self.txt_inp_log)
        
        ll.addWidget(QLabel("Stdout Log (stdout.log):"))
        self.txt_stdout_log = QTextEdit()
        self.txt_stdout_log.setReadOnly(True)
        self.txt_stdout_log.setFixedHeight(120)
        self.txt_stdout_log.setFontFamily("Consolas")
        self.txt_stdout_log.setFontPointSize(9)
        ll.addWidget(self.txt_stdout_log)

        ll.addWidget(QLabel("Stderr / Errors Log (stderr.log):"))
        self.txt_stderr_log = QTextEdit()
        self.txt_stderr_log.setReadOnly(True)
        self.txt_stderr_log.setFixedHeight(100)
        self.txt_stderr_log.setFontFamily("Consolas")
        self.txt_stderr_log.setFontPointSize(9)
        ll.addWidget(self.txt_stderr_log)
        
        bl.addWidget(log_card)
        bl.addStretch(1)

        scroll.setWidget(body)
        lay.addWidget(scroll)

    def refresh(self) -> None:
        """Reload configuration from disk and update status metrics."""
        cfg = load_persisted_config()
        
        # Populate form fields
        mode_idx = 0 if cfg.mode == IITPAVE_RUNNER_EXTERNAL else 1
        self.cb_mode.setCurrentIndex(mode_idx)
        self.spin_timeout.setValue(cfg.timeout_sec)
        self.chk_path_search.setChecked(cfg.include_path_search)
        
        # Perform environment validation
        validation = validate_iitpave_environment(
            configured_path=cfg.configured_executable_path or None,
            include_path_search=cfg.include_path_search,
        )
        
        # Populate candidates combo box
        self.cb_candidates.blockSignals(True)
        self.cb_candidates.clear()
        
        selected_candidate_text = ""
        for c in validation.candidates:
            source_lbl = f"{c.source.upper()}: {c.path}"
            if not c.exists:
                source_lbl += " (Not Found)"
            elif not c.is_file:
                source_lbl += " (Directory/Invalid)"
            self.cb_candidates.addItem(source_lbl, str(c.path))
            if validation.selected_path and c.path == validation.selected_path:
                selected_candidate_text = str(c.path)
        
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
        
        # Update badges
        if validation.selected_path:
            self.lbl_detection_badge.setText("Detected")
            self.lbl_detection_badge.setStyleSheet("background:#d4efdf; color:#196f3d; font-weight:bold; border-radius:4px; padding:2px;")
            self.lbl_selected_path.setText(f"Active Executable: <b>{validation.selected_path}</b>")
            
            # Version probing
            ver = detect_iitpave_version(validation.selected_path)
            self.lbl_detected_version.setText(f"Detected Version Info: <i>{ver}</i>")
        else:
            self.lbl_detection_badge.setText("Not Detected")
            self.lbl_detection_badge.setStyleSheet("background:#f9d5d5; color:#a81f1f; font-weight:bold; border-radius:4px; padding:2px;")
            self.lbl_selected_path.setText("Active Executable: <b>None (Checks are blocked from running)</b>")
            self.lbl_detected_version.setText("Detected Version Info: <b>None</b>")
            
        # Modes badge
        last_run = get_last_run_info()
        has_real_run = last_run is not None and last_run.get("status") == "success"
        
        if validation.selected_path and cfg.mode == IITPAVE_RUNNER_EXTERNAL and has_real_run:
            self.lbl_mode_badge.setText("Mechanistic Verified Mode")
            self.lbl_mode_badge.setStyleSheet("background:#d4e6f1; color:#1a5276; font-weight:bold; border-radius:4px; padding:2px;")
        else:
            self.lbl_mode_badge.setText("Decision Support Mode")
            self.lbl_mode_badge.setStyleSheet("background:#fef5d1; color:#a67c00; font-weight:bold; border-radius:4px; padding:2px;")

        # Populate logs
        if last_run:
            status_text = last_run.get("status", "unknown").upper()
            dur = last_run.get("duration_sec", 0.0)
            err = last_run.get("error", "")
            self.lbl_log_meta.setText(
                f"<b>Last Run Status:</b> {status_text}  ·  "
                f"<b>Timestamp:</b> {last_run.get('timestamp')}  ·  "
                f"<b>Duration:</b> {dur:.3f}s"
            )
            self.txt_inp_log.setPlainText(last_run.get("input", ""))
            self.txt_stdout_log.setPlainText(last_run.get("stdout", ""))
            
            stderr_txt = last_run.get("stderr", "")
            if err:
                stderr_txt = f"ERROR EXCEPTION:\n{err}\n\n" + stderr_txt
            self.txt_stderr_log.setPlainText(stderr_txt)
        else:
            self.lbl_log_meta.setText("No execution logged recently.")
            self.txt_inp_log.clear()
            self.txt_stdout_log.clear()
            self.txt_stderr_log.clear()

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
            
        # Try a safe probe
        version = detect_iitpave_version(path)
        QMessageBox.information(
            self,
            "Validation Successful",
            f"The executable is valid!\n\nDetected Info: {version}"
        )
        self.refresh()

    def _on_save_settings(self) -> None:
        path_str = self.txt_manual_path.text().strip()
        mode_str = IITPAVE_RUNNER_EXTERNAL if self.cb_mode.currentIndex() == 0 else IITPAVE_RUNNER_STUB
        
        cfg = IITPaveRunnerConfig(
            mode=mode_str,
            configured_executable_path=path_str,
            include_path_search=self.chk_path_search.isChecked(),
            timeout_sec=self.spin_timeout.value(),
        )
        
        try:
            save_persisted_config(cfg)
            QMessageBox.information(self, "Settings Saved", "IITPAVE integration settings saved successfully.")
            self.config_updated.emit()
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Failed to persist configuration: {e}")
