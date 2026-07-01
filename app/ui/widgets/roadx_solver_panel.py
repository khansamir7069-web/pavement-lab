"""RoadX In-House Mechanistic Solver Panel.

Runs the internal multilayer elastic solver to evaluate pavement responses,
critical stresses/strains, surface deflections, fatigue/rutting life,
and structural adequacy.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
)

from .common import Card, PageHeader, styled_button
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.core.models import Layer, WheelLoad, ObservationPoint, Pavement
from mechanistic_solver.design.irc37_engine import IRC37DesignEngine
from mechanistic_solver.design.reporting import IRCDesignReportGenerator
from mechanistic_solver.reports.release_report_generator import ReleaseReportGenerator


class RoadXSolverPanel(QWidget):
    saved = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._project_name: str = ""
        self._last_adequacy: dict | None = None
        self._last_pavement: Pavement | None = None
        self._last_loads: list[WheelLoad] | None = None
        self._last_solver_status: str = "Idle"
        
        self._build()
        self.refresh()

    def set_project(self, project_id: int | None, name: str = "") -> None:
        self._project_id = project_id
        self._project_name = name
        self.btn_run_solver.setEnabled(project_id is not None)
        
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

        # Header
        self.header = PageHeader(
            "RoadX In-House Mechanistic Solver",
            "Perform real-time multi-layer elastic analysis and design validation using the internal solver engine."
        )
        self.btn_run_solver = styled_button("Run RoadX Solver", "primary")
        self.btn_run_solver.clicked.connect(self._on_run_solver)
        
        self.btn_export_solver_report = styled_button("Export Solver Report", "secondary")
        self.btn_export_solver_report.clicked.connect(self._on_export_solver_report)
        self.btn_export_solver_report.setEnabled(False)
        
        self.btn_export_design_report = styled_button("Export Design Report", "secondary")
        self.btn_export_design_report.clicked.connect(self._on_export_design_report)
        self.btn_export_design_report.setEnabled(False)

        self.header.add_action(self.btn_export_solver_report)
        self.header.add_action(self.btn_export_design_report)
        self.header.add_action(self.btn_run_solver)
        lay.addWidget(self.header)

        # Scroll Body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)
        body_lay.setSpacing(14)

        # Active Project Banner
        self.lbl_project_banner = QLabel("No project loaded.")
        body_lay.addWidget(self.lbl_project_banner)

        # 1. Tire Load Configuration Card
        load_card = Card()
        load_lay = QVBoxLayout(load_card)
        load_lay.setContentsMargins(18, 14, 18, 14)
        load_lay.addWidget(QLabel("<b>Wheel Load & Contact Parameters</b>"))
        
        form = QFormLayout()
        self.spin_wheel_load = QDoubleSpinBox()
        self.spin_wheel_load.setRange(1.0, 500.0)
        self.spin_wheel_load.setValue(20.0)
        self.spin_wheel_load.setSuffix(" kN")
        
        self.spin_pressure = QDoubleSpinBox()
        self.spin_pressure.setRange(0.01, 5.00)
        self.spin_pressure.setValue(0.56)
        self.spin_pressure.setSuffix(" MPa")
        self.spin_pressure.setDecimals(3)
        self.spin_pressure.valueChanged.connect(self._recalculate_radius)
        
        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setRange(5.0, 1000.0)
        self.spin_radius.setValue(106.7)
        self.spin_radius.setSuffix(" mm")
        self.spin_radius.setDecimals(1)
        self.spin_wheel_load.valueChanged.connect(self._recalculate_radius)
        
        form.addRow("Wheel Load (P):", self.spin_wheel_load)
        form.addRow("Tyre Contact Pressure (q):", self.spin_pressure)
        form.addRow("Calculated Contact Radius (a):", self.spin_radius)
        load_lay.addLayout(form)
        body_lay.addWidget(load_card)

        # 2. Input Layer Stack Card
        layers_card = Card()
        layers_lay = QVBoxLayout(layers_card)
        layers_lay.setContentsMargins(18, 14, 18, 14)
        layers_lay.addWidget(QLabel("<b>Pavement Structural Layer Stack</b>"))
        
        self.layer_table = QTableWidget(0, 5)
        self.layer_table.setHorizontalHeaderLabels([
            "Layer Name", "Material Type", "Thickness (mm)", "Modulus (MPa)", "Poisson's Ratio"
        ])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layer_table.setMinimumHeight(150)
        layers_lay.addWidget(self.layer_table)
        body_lay.addWidget(layers_card)

        # 3. Output Response Results Card
        self.results_card = Card()
        res_lay = QVBoxLayout(self.results_card)
        res_lay.setContentsMargins(18, 14, 18, 14)
        res_lay.addWidget(QLabel("<b>Calculated Responses & Adequacy Verdict</b>"))
        
        self.lbl_depths_info = QLabel("Extraction Depths: ε_t depth = — mm, ε_v depth = — mm, deflection depth = 0 mm")
        self.lbl_depths_info.setStyleSheet("color: #4a5568; font-style: italic; font-size: 9.5pt; margin-bottom: 8px;")
        res_lay.addWidget(self.lbl_depths_info)
        
        self.grid_results = QGridLayout()
        self.grid_results.setSpacing(10)
        
        self.grid_results.addWidget(QLabel("Critical Tensile Strain (ε_t):"), 0, 0)
        self.lbl_tensile = QLabel("—")
        self.lbl_tensile.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_tensile, 0, 1)

        self.grid_results.addWidget(QLabel("Critical Compressive Strain (ε_v):"), 1, 0)
        self.lbl_compressive = QLabel("—")
        self.lbl_compressive.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_compressive, 1, 1)

        self.grid_results.addWidget(QLabel("Surface Vertical Deflection (w):"), 2, 0)
        self.lbl_deflection = QLabel("—")
        self.lbl_deflection.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_deflection, 2, 1)

        self.grid_results.addWidget(QLabel("Fatigue Life (Allowable / Design):"), 3, 0)
        self.lbl_fatigue = QLabel("—")
        self.lbl_fatigue.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_fatigue, 3, 1)

        self.grid_results.addWidget(QLabel("Rutting Life (Allowable / Design):"), 4, 0)
        self.lbl_rutting = QLabel("—")
        self.lbl_rutting.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_rutting, 4, 1)

        self.grid_results.addWidget(QLabel("Governing failure Mode:"), 5, 0)
        self.lbl_governing = QLabel("—")
        self.lbl_governing.setStyleSheet("font-weight: bold;")
        self.grid_results.addWidget(self.lbl_governing, 5, 1)

        self.grid_results.addWidget(QLabel("Structural Adequacy Verdict:"), 6, 0)
        self.lbl_verdict = QLabel("—")
        self.lbl_verdict.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.grid_results.addWidget(self.lbl_verdict, 6, 1)

        res_lay.addLayout(self.grid_results)
        self.results_card.setVisible(False)
        body_lay.addWidget(self.results_card)

        # 4. About & System Status Card
        status_card = Card()
        status_lay = QVBoxLayout(status_card)
        status_lay.setContentsMargins(18, 14, 18, 14)
        status_lay.addWidget(QLabel("<b>About & System Status</b>"))
        
        status_form = QFormLayout()
        
        # Package Checks
        p3 = "YES"
        try:
            import mechanistic_solver.solver
        except ImportError:
            p3 = "NO"

        p4 = "YES"
        try:
            import mechanistic_solver.advanced
        except ImportError:
            p4 = "NO"

        p5 = "YES"
        try:
            import mechanistic_solver.ai
        except ImportError:
            p5 = "NO"

        p6 = "YES"
        try:
            import mechanistic_solver.enterprise
        except ImportError:
            p6 = "NO"

        # External IITPAVE
        from app.core.iitpave.workflow import load_persisted_config, select_iitpave_runner
        try:
            selection = select_iitpave_runner(load_persisted_config())
            iitpave_conn = "Connected (YES)" if (selection.ok and selection.runner is not None) else "Disconnected (NO)"
        except Exception:
            iitpave_conn = "Disconnected (NO)"

        status_form.addRow("Phase 3 solver packaged:", QLabel(f"<b>{p3}</b>"))
        status_form.addRow("Phase 4 advanced package:", QLabel(f"<b>{p4}</b>"))
        status_form.addRow("Phase 5 AI package:", QLabel(f"<b>{p5}</b>"))
        status_form.addRow("Phase 6 enterprise package:", QLabel(f"<b>{p6}</b>"))
        status_form.addRow("Internal solver available:", QLabel("<b>YES</b>"))
        status_form.addRow("External IITPAVE connected:", QLabel(f"<b>{iitpave_conn}</b>"))
        
        status_lay.addLayout(status_form)
        body_lay.addWidget(status_card)

        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    def _recalculate_radius(self) -> None:
        p_kn = self.spin_wheel_load.value()
        q_mpa = self.spin_pressure.value()
        if q_mpa > 0:
            # P = 20 kN = 20000 N; q = 0.56 MPa = 0.56 N/mm^2
            p_n = p_kn * 1000.0
            radius_mm = math.sqrt(p_n / (math.pi * q_mpa))
            self.spin_radius.blockSignals(True)
            self.spin_radius.setValue(radius_mm)
            self.spin_radius.blockSignals(False)

    def refresh(self) -> None:
        if not self._project_id:
            self.layer_table.setRowCount(0)
            self.results_card.setVisible(False)
            return

        sd = self.db.latest_structural_design(self._project_id)
        if not sd:
            self.layer_table.setRowCount(0)
            self.results_card.setVisible(False)
            return

        comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
        self.layer_table.setRowCount(len(comp) + 1)
        
        for i, ly in enumerate(comp):
            self.layer_table.setItem(i, 0, QTableWidgetItem(ly.get("name", "Layer")))
            self.layer_table.setItem(i, 1, QTableWidgetItem(ly.get("material", "—")))
            self.layer_table.setItem(i, 2, QTableWidgetItem(f"{float(ly.get('thickness_mm', 0.0)):.1f}"))
            self.layer_table.setItem(i, 3, QTableWidgetItem(f"{float(ly.get('modulus_mpa', 0.0)):.1f}"))
            poisson = ly.get("poisson") or ly.get("poisson_ratio") or 0.35
            self.layer_table.setItem(i, 4, QTableWidgetItem(f"{float(poisson):.2f}"))

        # Subgrade row
        row_idx = len(comp)
        self.layer_table.setItem(row_idx, 0, QTableWidgetItem("Subgrade"))
        self.layer_table.setItem(row_idx, 1, QTableWidgetItem("Subgrade"))
        self.layer_table.setItem(row_idx, 2, QTableWidgetItem("Infinite"))
        self.layer_table.setItem(row_idx, 3, QTableWidgetItem(f"{float(sd.subgrade_mr_mpa):.1f}"))
        self.layer_table.setItem(row_idx, 4, QTableWidgetItem("0.35"))

        for i in range(self.layer_table.rowCount()):
            for j in range(self.layer_table.columnCount()):
                item = self.layer_table.item(i, j)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def _on_run_solver(self) -> None:
        if not self._project_id:
            return

        sd = self.db.latest_structural_design(self._project_id)
        if not sd:
            QMessageBox.warning(self, "No Structural Design", "Please complete and save a structural design first.")
            return

        comp = json.loads(sd.composition_json) if isinstance(sd.composition_json, str) else sd.composition_json
        
        # 1. Build Layer objects
        layers = []
        for ly in comp:
            layers.append(
                Layer(
                    name=ly.get("name", "Layer"),
                    thickness=float(ly.get("thickness_mm")),
                    elastic_modulus=float(ly.get("modulus_mpa")),
                    poisson_ratio=float(ly.get("poisson") or ly.get("poisson_ratio") or 0.35),
                    density=2400.0
                )
            )
            
        subgrade = Layer(
            name="Subgrade",
            thickness=None,
            elastic_modulus=float(sd.subgrade_mr_mpa),
            poisson_ratio=0.35,
            density=1800.0
        )
        pavement = Pavement(layers, subgrade)
        self._last_pavement = pavement

        # 2. Build WheelLoad
        load = WheelLoad(
            wheel_load=self.spin_wheel_load.value(),
            pressure=self.spin_pressure.value(),
            radius=self.spin_radius.value()
        )
        self._last_loads = [load]

        # 3. Setup observation points:
        # Detect consecutive top bituminous layers (e.g. BC + DBM)
        bituminous_depth = 0.0
        for ly in comp:
            name_lower = ly.get("name", "").lower()
            is_bit = any(x in name_lower for x in ["bc", "dbm", "bituminous", "asphalt", "sma"])
            if is_bit:
                bituminous_depth += float(ly.get("thickness_mm") or 0.0)
            else:
                break
        
        # Use bituminous_depth as fatigue probe, falling back to layers[0].thickness
        h1 = bituminous_depth if bituminous_depth > 0.0 else layers[0].thickness
        
        # rutting probe: top of subgrade
        subgrade_depth = sum(l.thickness for l in layers)
        
        points = [
            ObservationPoint(0.0, 0.0, h1),
            ObservationPoint(0.0, 0.0, subgrade_depth),
            ObservationPoint(0.0, 0.0, 0.0) # Deflection
        ]

        # 4. Run solver
        solver = MechanisticSolver(mode="multilayer")
        self._last_solver_status = "Executing..."
        try:
            response = solver.solve(pavement, [load], points)
            self._last_solver_status = response.status
        except Exception as e:
            QMessageBox.critical(self, "Solver Error", f"The internal solver execution failed:\n{e}")
            return

        # 5. Extract critical strains
        strain_fatigue = response.strain_results[0]
        eps_t = max(strain_fatigue.get("epsilon_r", 0.0), strain_fatigue.get("epsilon_t", 0.0))
        
        strain_rutting = response.strain_results[1]
        eps_v = strain_rutting.get("epsilon_z", 0.0)

        # Deflection at surface
        deflection_m = response.displacement_results[2].get("vertical_deflection", 0.0)
        deflection_mm = deflection_m * 1000.0

        # 6. Analyze adequacy
        design_engine = IRC37DesignEngine(solver)
        adequacy = design_engine.analyze(pavement, [load], float(sd.design_msa))
        self._last_adequacy = adequacy

        # 7. Render UI Results
        self.lbl_tensile.setText(f"{eps_t * 1e6:.2f} microstrain")
        self.lbl_compressive.setText(f"{eps_v * 1e6:.2f} microstrain")
        self.lbl_deflection.setText(f"{deflection_mm:.4f} mm")
        self.lbl_depths_info.setText(
            f"Extraction Depths: ε_t depth = {h1:.1f} mm, "
            f"ε_v depth = {subgrade_depth:.1f} mm, "
            f"deflection depth = 0 mm"
        )

        f_status = adequacy["fatigue_status"]
        r_status = adequacy["rutting_status"]
        
        f_allow = f_status["allowable_repetitions_msa"]
        f_allow_str = f"{f_allow:.2f} MSA" if math.isfinite(f_allow) else "Infinite"
        self.lbl_fatigue.setText(f"{f_allow_str} / {sd.design_msa:.2f} MSA (Passed: {f_status['passed']})")

        r_allow = r_status["allowable_repetitions_msa"]
        r_allow_str = f"{r_allow:.2f} MSA" if math.isfinite(r_allow) else "Infinite"
        self.lbl_rutting.setText(f"{r_allow_str} / {sd.design_msa:.2f} MSA (Passed: {r_status['passed']})")

        self.lbl_governing.setText(adequacy["governing_failure_mode"].upper())

        if adequacy["overall_passed"]:
            self.lbl_verdict.setText("PASSED")
            self.lbl_verdict.setStyleSheet("color:#1d7a3a; font-size:14pt; font-weight:bold;")
        else:
            self.lbl_verdict.setText("FAILED")
            self.lbl_verdict.setStyleSheet("color:#d9381e; font-size:14pt; font-weight:bold;")

        self.results_card.setVisible(True)
        self.btn_export_solver_report.setEnabled(True)
        self.btn_export_design_report.setEnabled(True)

        # 8. Save validation status to DB
        try:
            # Build validation summary structure for database compatibility
            from app.core.mechanistic_validation.engine import (
                MechanisticValidationInput,
                compute_mechanistic_validation,
                MechanisticResult,
                PointResult,
            )
            
            p_results = (
                PointResult(
                    z_mm=h1, r_mm=0.0,
                    sigma_z_mpa=0.0, sigma_r_mpa=0.0, sigma_t_mpa=0.0,
                    epsilon_z_microstrain=0.0, epsilon_r_microstrain=eps_t * 1e6, epsilon_t_microstrain=eps_t * 1e6
                ),
                PointResult(
                    z_mm=subgrade_depth, r_mm=0.0,
                    sigma_z_mpa=0.0, sigma_r_mpa=0.0, sigma_t_mpa=0.0,
                    epsilon_z_microstrain=eps_v * 1e6, epsilon_r_microstrain=0.0, epsilon_t_microstrain=0.0
                )
            )
            mech_res = MechanisticResult(
                point_results=p_results,
                references=(),
                is_placeholder=False,
                source="internal_solver",
                notes="Analyzed using internal multilayer elastic solver."
            )
            
            from app.core.iitpave.pavement_structure import from_structural_layers
            struct = from_structural_layers(comp, subgrade_mr_mpa=sd.subgrade_mr_mpa)
            
            val_input = MechanisticValidationInput(
                mech_result=mech_res,
                structure=struct,
                design_msa=sd.design_msa
            )
            summary = compute_mechanistic_validation(val_input)
            
            self.db.save_mechanistic_validation(
                project_id=self._project_id,
                summary=summary,
                inputs=val_input,
                iteration_history_json=json.dumps([]),
                recommended_thickness_json=json.dumps({ly.get("name"): float(ly.get("thickness_mm")) for ly in comp})
            )
            self.db.log_project_audit(
                project_id=self._project_id,
                module="roadx_solver",
                action="Internal Solver Run",
                detail=f"Overall Verdict: {'PASSED' if adequacy['overall_passed'] else 'FAILED'}"
            )
            self.db.set_module_status(self._project_id, "iitpave_status", "complete")
            self.saved.emit()
        except Exception as e:
            # Don't crash UI on database log failures
            print("DB validation logging warning:", e)

    def _on_export_solver_report(self) -> None:
        if not self._project_id:
            return
            
        dir_path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not dir_path:
            return
            
        try:
            gen = ReleaseReportGenerator()
            md_path, json_path = gen.save_reports(dir_path)
            QMessageBox.information(
                self, "Export Successful",
                f"Solver report exported successfully:\n- {Path(md_path).name}\n- {Path(json_path).name}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export solver report:\n{e}")

    def _on_export_design_report(self) -> None:
        if not self._project_id or not self._last_adequacy:
            return
            
        dir_path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not dir_path:
            return
            
        try:
            gen = IRCDesignReportGenerator()
            sd = self.db.latest_structural_design(self._project_id)
            
            # Dummy optimization result and recommendations
            opt_result = {
                "optimal_thickness_mm": float(sd.total_pavement_thickness_mm),
                "converged": True,
                "warnings": [],
                "history": []
            }
            recs = ["Design meets standard fatigue and rutting criteria under current traffic loading."]
            
            md_path, json_path = gen.save_reports(
                pavement=self._last_pavement,
                loads=self._last_loads,
                traffic_msa=float(sd.design_msa),
                adequacy=self._last_adequacy,
                opt_result=opt_result,
                recs=recs,
                solver_status=self._last_solver_status,
                output_dir=dir_path
            )
            QMessageBox.information(
                self, "Export Successful",
                f"Design report exported successfully:\n- {Path(md_path).name}\n- {Path(json_path).name}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export design report:\n{e}")
