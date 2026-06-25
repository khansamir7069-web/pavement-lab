"""Pavement Lab — main desktop window."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __version__
from app.config import REPORTS_DIR
from app.core import (
    build_deployment_packaging_checklist,
    compute_material_calc,
    compute_mix_design,
    format_deployment_checklist_item_text,
)
from app.core.import_summary import ImportedMixResult, parse_summary_excel
from app.core.models import MixDesignInput, ProjectInfo
from app.db import get_db
from app.db.project_exchange import (
    ProjectImportError,
    export_project,
    import_project,
    read_project_export,
    write_project_export,
)
from app.graphs import build_chart_set
from app.reports import (
    CombinedReportContext,
    ConditionReportContext,
    MaintenanceReportContext,
    MaterialQuantityReportContext,
    ReportContext,
    StructuralReportContext,
    TrafficReportContext,
    StabilizedReportContext,
    build_combined_report,
    build_condition_docx,
    IITPaveSchemaReportContext,
    build_maintenance_docx,
    build_material_quantity_docx,
    build_mix_design_docx,
    build_structural_docx,
    build_stabilized_docx,
    build_traffic_docx,
    build_iitpave_schema_history_review,
    build_iitpave_schema_history_selection_audit_review,
    build_report_revision_history_review,
    format_iitpave_schema_history_item_text,
    format_iitpave_schema_history_selection_audit_item_text,
    format_report_revision_snapshot_text,
    run_iitpave_schema_diagnostics_workflow,
)
from app.reports.word_report import export_to_pdf

from .widgets.common import Card
from .widgets.dashboard import Dashboard
from .widgets.inputs_panel import InputsPanel
from .widgets.condition_survey_panel import ConditionSurveyPanel
from .widgets.maintenance_panel import MaintenancePanel
from .widgets.material_qty_panel import MaterialQuantityPanel
from .widgets.traffic_panel import TrafficPanel
from .widgets.module_hub import ModuleHub
from .widgets.project_form import ProjectForm
from .widgets.results_panel import ResultsPanel
from .widgets.spec_admin import SpecAdminPanel
from .widgets.structural_panel import StructuralPanel
from .widgets.stabilized_panel import StabilizedPanel
from .widgets.iitpave_status_panel import IITPaveStatusPanel
from .widgets.subgrade_panel import SubgradePanel
from .widgets.engineering_review_panel import EngineeringReviewPanel
from .widgets.submission_panel import SubmissionPanel


log = logging.getLogger(__name__)


SIDEBAR_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Module Hub", "hub"),
    ("1. Project Setup", "project"),
    ("2. Traffic Survey / MSA", "traffic"),
    ("3. Subgrade / CBR", "subgrade"),
    ("4. Pavement Structural Design", "structural"),
    ("5. Alternative Selection", "stabilized"),
    ("6. IITPAVE Verification", "iitpave_status"),
    ("7. Mix Design", "inputs"),
    ("8. BOQ", "material_qty"),
    ("9. Engineering Review", "engineering_review"),
    ("10. Submission", "submission"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = get_db()
        self._current_project_id: int | None = None
        self._last_result = None
        self._last_material_calc = None
        self._last_inputs_payload: dict | None = None
        self._last_chart_set = None
        self._build()
        self._wire_signals()
        self.dashboard.refresh()
        self._show_page("dashboard")

    def _build(self) -> None:
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1320, 820)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        brand = QLabel(f"⛏  {__app_name__}")
        brand.setObjectName("SidebarBrand")
        sb_layout.addWidget(brand)
        tag = QLabel("Pavement / Bituminous Mix Lab")
        tag.setObjectName("SidebarTag")
        sb_layout.addWidget(tag)

        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        for label, key in SIDEBAR_ITEMS:
            QListWidgetItem(label, self.nav).setData(Qt.UserRole, key)
        sb_layout.addWidget(self.nav, stretch=1)

        # Developer / Debug Tools container (hidden behind Ctrl+Shift+D by default)
        self.dev_tools_widget = QWidget()
        dev_lay = QVBoxLayout(self.dev_tools_widget)
        dev_lay.setContentsMargins(0, 0, 0, 0)
        dev_lay.setSpacing(6)

        # Import button at bottom of sidebar
        self.btn_import = QPushButton("⬆  Import Summary Excel")
        self.btn_import.setObjectName("ImportBtn")
        self.btn_import.setToolTip(
            "Load a pre-computed Marshall summary table from an Excel file\n"
            "(Pb %, Gmm, Gmb, VIM, VMA, VFB, Stability, Flow, MQ)."
        )
        self.btn_import.clicked.connect(self._on_import_summary)
        dev_lay.addWidget(self.btn_import)

        self.btn_iitpave_schema = QPushButton("IITPAVE Schema Diagnostics")
        self.btn_iitpave_schema.setObjectName("ImportBtn")
        self.btn_iitpave_schema.setToolTip(
            "Select a local IITPAVE output fixture folder and generate an "
            "audit-only schema diagnostics report. No engineering calculations "
            "are performed."
        )
        self.btn_iitpave_schema.clicked.connect(self._on_iitpave_schema_diagnostics)
        dev_lay.addWidget(self.btn_iitpave_schema)

        self.btn_iitpave_schema_history = QPushButton("IITPAVE Schema History")
        self.btn_iitpave_schema_history.setObjectName("ImportBtn")
        self.btn_iitpave_schema_history.setToolTip(
            "Review persisted IITPAVE schema diagnostics history for the "
            "active project. No engineering calculations are performed."
        )
        self.btn_iitpave_schema_history.clicked.connect(self._on_iitpave_schema_history)
        dev_lay.addWidget(self.btn_iitpave_schema_history)

        self.btn_iitpave_schema_report_audit = QPushButton("IITPAVE Report Audit")
        self.btn_iitpave_schema_report_audit.setObjectName("ImportBtn")
        self.btn_iitpave_schema_report_audit.setToolTip(
            "Review report-time IITPAVE schema-history selection audit records "
            "for the active project. Records are read-only."
        )
        self.btn_iitpave_schema_report_audit.clicked.connect(
            self._on_iitpave_schema_report_audit
        )
        dev_lay.addWidget(self.btn_iitpave_schema_report_audit)

        self.btn_report_revisions = QPushButton("Report Revisions")
        self.btn_report_revisions.setObjectName("ImportBtn")
        self.btn_report_revisions.setToolTip(
            "Review read-only report revision snapshots for the active project."
        )
        self.btn_report_revisions.clicked.connect(self._on_report_revisions)
        dev_lay.addWidget(self.btn_report_revisions)

        self.btn_deployment_diagnostics = QPushButton("Deployment Diagnostics")
        self.btn_deployment_diagnostics.setObjectName("ImportBtn")
        self.btn_deployment_diagnostics.setToolTip(
            "Review local-only deployment packaging readiness diagnostics. "
            "No installer, activation, licensing, or cloud deployment is performed."
        )
        self.btn_deployment_diagnostics.clicked.connect(self._on_deployment_diagnostics)
        dev_lay.addWidget(self.btn_deployment_diagnostics)

        self.dev_tools_widget.setVisible(False)
        sb_layout.addWidget(self.dev_tools_widget)

        # Wire developer tools shortcut Ctrl+Shift+D
        from PySide6.QtGui import QKeySequence, QShortcut
        self.shortcut_dev = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.shortcut_dev.activated.connect(self._toggle_developer_tools)

        version_lbl = QLabel(f"RoadX Professional Suite v{__version__}\nby SKM Technologies")
        version_lbl.setObjectName("SidebarTag")
        version_lbl.setAlignment(Qt.AlignCenter)
        version_lbl.setStyleSheet("color: #718096; font-size: 8pt; margin-top: 10px; margin-bottom: 10px;")
        sb_layout.addWidget(version_lbl)

        lay.addWidget(sidebar)

        # Stack
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, stretch=1)

        self.dashboard = Dashboard(self.db)
        self.project_form = ProjectForm(self.db)
        self.hub = ModuleHub()
        self.inputs = InputsPanel()
        self.results = ResultsPanel()
        self.spec_admin = SpecAdminPanel()
        self.structural = StructuralPanel(self.db)
        self.stabilized = StabilizedPanel(self.db)
        self.maintenance = MaintenancePanel(self.db)
        self.material_qty = MaterialQuantityPanel(self.db)
        self.traffic = TrafficPanel(self.db)
        self.condition = ConditionSurveyPanel(self.db)
        self.iitpave_status = IITPaveStatusPanel(self.db)
        self.subgrade = SubgradePanel(self.db)
        self.engineering_review = EngineeringReviewPanel(self.db)
        self.submission = SubmissionPanel(self.db)

        # Wire Back buttons on every page's header.
        # Lambdas must swallow Qt's clicked(bool) positional arg with *_.
        from .widgets.common import PageHeader
        back_routes = (
            (self.project_form, "dashboard"),
            (self.inputs,       "hub"),
            (self.results,      "inputs"),
            (self.spec_admin,   "hub"),
            (self.structural,   "hub"),
            (self.stabilized,   "hub"),
            (self.maintenance,  "hub"),
            (self.material_qty, "hub"),
            (self.traffic,      "hub"),
            (self.condition,    "hub"),
            (self.iitpave_status, "hub"),
            (self.subgrade,     "hub"),
            (self.engineering_review, "hub"),
            (self.submission,   "hub"),
        )
        for w, target in back_routes:
            hdr = w.findChild(PageHeader)
            if hdr is not None:
                hdr.enable_back(lambda *_, t=target: self._show_page(t))

        # Stack pages mapping (contains all pages, even legacy ones)
        all_pages = {
            "dashboard": self.dashboard,
            "project": self.project_form,
            "hub": self.hub,
            "inputs": self.inputs,
            "results": self.results,
            "specs_admin": self.spec_admin,
            "structural": self.structural,
            "stabilized": self.stabilized,
            "maintenance": self.maintenance,
            "material_qty": self.material_qty,
            "traffic": self.traffic,
            "condition": self.condition,
            "iitpave_status": self.iitpave_status,
            "subgrade": self.subgrade,
            "engineering_review": self.engineering_review,
            "submission": self.submission,
        }
        
        self._page_keys = {}
        for key, w in all_pages.items():
            idx = self.stack.addWidget(w)
            self._page_keys[key] = idx

        # Status
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"{__app_name__} ready  •  DB: {self.db.path}")

    def _wire_signals(self) -> None:
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.dashboard.new_project.connect(self._on_new_project)
        self.dashboard.open_project.connect(self._on_open_project)
        self.dashboard.delete_project.connect(self._on_delete_project)
        self.dashboard.export_project.connect(self._on_export_project)
        self.dashboard.import_project.connect(self._on_import_project_export)
        self.dashboard.load_demo_project_triggered.connect(self._on_load_demo_project)
        self.project_form.saved.connect(self._on_project_saved)
        self.hub.module_selected.connect(self._on_module_selected)
        self.structural.saved.connect(self._on_structural_saved)
        self.structural.export_requested.connect(self._on_export_structural)
        self.stabilized.saved.connect(self._on_stabilized_saved)
        self.stabilized.export_requested.connect(self._on_export_stabilized)
        self.maintenance.saved.connect(self._on_maintenance_saved)
        self.maintenance.export_requested.connect(self._on_export_maintenance)
        self.material_qty.saved.connect(self._on_material_qty_saved)
        self.material_qty.export_requested.connect(self._on_export_material_qty)
        self.material_qty.export_excel_requested.connect(self._on_export_material_excel)
        self.traffic.saved.connect(self._on_traffic_saved)
        self.traffic.export_requested.connect(self._on_export_traffic)
        self.condition.saved.connect(self._on_condition_saved)
        self.condition.export_requested.connect(self._on_export_condition)
        self.inputs.compute_requested.connect(self._on_compute)
        self.inputs.reset_requested.connect(self._on_reset_inputs)
        self.results.generate_word.connect(self._on_export_word)
        self.results.generate_pdf.connect(self._on_export_pdf)
        self.subgrade.saved.connect(self._refresh_hub)
        self.engineering_review.saved.connect(self._refresh_hub)
        self.submission.saved.connect(self._refresh_hub)
        self.submission.project_changed.connect(self._on_open_project)
        self.hub.status_changed.connect(self._on_hub_status_changed)

    def _on_hub_status_changed(self, key: str, status: str) -> None:
        if self._current_project_id is not None:
            self.db.set_module_status(self._current_project_id, key, status)
            self._refresh_hub()

    def _on_iitpave_config_updated(self) -> None:
        self.statusBar().showMessage("IITPAVE configuration updated.")

    def _toggle_developer_tools(self) -> None:
        self.dev_tools_widget.setVisible(self.dev_tools_widget.isHidden())

    # ----- navigation -----

    def _show_page(self, key: str) -> None:
        idx = self._page_keys[key]
        self.stack.setCurrentIndex(idx)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)

        # Dynamic design lock UI traversal
        widget = self.stack.currentWidget()
        if widget:
            p = self.db.get_project(self._current_project_id) if self._current_project_id else None
            project_locked = p.locked if p else False
            
            module_status = self.db.get_module_status(self._current_project_id) if self._current_project_id else {}
            status_key = {
                "project": "project",
                "traffic": "traffic",
                "subgrade": "subgrade",
                "structural": "structural",
                "stabilized": "stabilized",
                "iitpave_status": "iitpave_status",
                "inputs": "mix_design",
                "results": "mix_design",
                "material_qty": "material_qty",
                "engineering_review": "engineering_review",
                "submission": "submission",
            }.get(key, key)
            
            module_locked = module_status.get(status_key) == "locked"
            locked = project_locked or module_locked

            # Display lock status in statusBar
            if locked:
                self.statusBar().showMessage(f"Project #{self._current_project_id} stage '{status_key}' is LOCKED.")
            else:
                if self._current_project_id:
                    self.statusBar().showMessage(f"Project #{self._current_project_id} loaded.")
                else:
                    self.statusBar().showMessage("Ready")

            # submission manages its own lock UI state in set_project()
            if widget != self.submission:
                # Disable buttons
                for btn in widget.findChildren(QPushButton):
                    txt = btn.text().lower()
                    if any(x in txt for x in ["save", "compute", "calculate", "reset", "clear", "delete", "import"]):
                        if "zip" not in txt and "export" not in txt and "unlock" not in txt:
                            btn.setEnabled(not locked)
                
                # Disable input fields
                for box in widget.findChildren(QLineEdit):
                    box.setEnabled(not locked)
                for box in widget.findChildren(QComboBox):
                    box.setEnabled(not locked)
                for box in widget.findChildren(QTextEdit):
                    box.setEnabled(not locked)
                from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QCheckBox
                for box in widget.findChildren(QSpinBox):
                    box.setEnabled(not locked)
                for box in widget.findChildren(QDoubleSpinBox):
                    box.setEnabled(not locked)
                for box in widget.findChildren(QCheckBox):
                    box.setEnabled(not locked)

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav.item(row).data(Qt.UserRole)
        self.stack.setCurrentIndex(self._page_keys[key])
        
        p = self.db.get_project(self._current_project_id) if self._current_project_id else None
        work_name = p.work_name if p else ""
        
        if key == "dashboard":
            self.dashboard.refresh()
        elif key == "iitpave_status":
            self.iitpave_status.refresh()
        elif key == "subgrade":
            self.subgrade.set_project(self._current_project_id, work_name)
        elif key == "inputs":
            if self._current_project_id:
                self.inputs.set_project(self._current_project_id, self.db)
        elif key == "engineering_review":
            self.engineering_review.set_project(self._current_project_id, work_name)
        elif key == "submission":
            self.submission.set_project(self._current_project_id, work_name)
        elif key == "traffic":
            self.traffic.set_project(self._current_project_id, work_name)
        elif key == "structural":
            self.structural.set_project(self._current_project_id, work_name)
        elif key == "stabilized":
            self.stabilized.set_project(self._current_project_id, work_name)
        elif key == "material_qty":
            self.material_qty.set_project(self._current_project_id, work_name)
        elif key == "project":
            self.project_form.load_project(self._current_project_id)

    # ----- project lifecycle -----

    def _on_new_project(self) -> None:
        self._current_project_id = None
        self.project_form.load_project(None)
        self._show_page("project")

    def _on_open_project(self, project_id: int) -> None:
        self._current_project_id = project_id
        self.project_form.load_project(project_id)
        self._refresh_hub()
        self._show_page("hub")

    def _on_load_demo_project(self) -> None:
        from app.db.schema import Project
        from sqlalchemy import select
        from datetime import datetime
        
        with self.db.session() as s:
            existing_demo = s.scalars(
                select(Project).where(Project.work_name == "NH-48 Flexible Pavement Demo")
            ).first()
            
        if existing_demo is not None:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Demo Project Exists")
            msg_box.setText(
                "The project 'NH-48 Flexible Pavement Demo' already exists.\n\n"
                "Please choose how you would like to proceed:"
            )
            
            open_btn = msg_box.addButton("Open Existing Demo", QMessageBox.ActionRole)
            copy_btn = msg_box.addButton("Create Fresh Copy", QMessageBox.ActionRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            
            msg_box.setDefaultButton(open_btn)
            msg_box.exec()
            
            clicked = msg_box.clickedButton()
            if clicked == open_btn:
                self._on_open_project(existing_demo.id)
            elif clicked == copy_btn:
                suffix = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                from app.demo.demo_project_loader import create_demo_project
                try:
                    new_id = create_demo_project(self.db, name_suffix=suffix)
                    QMessageBox.information(
                        self, "Success",
                        f"Fresh copy of the demo project created successfully:\n"
                        f"NH-48 Flexible Pavement Demo (Copy - {suffix})"
                    )
                    self._on_open_project(new_id)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create fresh copy: {e}")
            else:
                return
        else:
            from app.demo.demo_project_loader import create_demo_project
            try:
                new_id = create_demo_project(self.db)
                QMessageBox.information(
                    self, "Success",
                    "Demo project 'NH-48 Flexible Pavement Demo' loaded successfully."
                )
                self._on_open_project(new_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load demo project: {e}")

    def _on_project_saved(self, project_id: int) -> None:
        self._current_project_id = project_id
        self.statusBar().showMessage(f"Project #{project_id} saved.")
        self._refresh_hub()
        self._show_page("hub")

    def _refresh_hub(self) -> None:
        if self._current_project_id is None:
            self.hub.set_project(None, "")
            return
        p = self.db.get_project(self._current_project_id)
        status = self.db.get_module_status(self._current_project_id)
        self.hub.set_project(
            self._current_project_id,
            p.work_name if p else "",
            status,
        )

    def _on_module_selected(self, key: str) -> None:
        """Route user from Hub into the chosen module with sequence gates."""
        if self._current_project_id is None:
            QMessageBox.warning(self, "No project", "Please save a project first.")
            self._show_page("project")
            return

        p = self.db.get_project(self._current_project_id)
        if not p:
            return

        is_legacy = bool(p.is_legacy)
        status = self.db.get_module_status(self._current_project_id)

        # Gate 1: Mix Design requires Pavement Structural Design
        if key == "mix_design":
            if status.get("structural") != "complete":
                if not is_legacy:
                    QMessageBox.warning(
                        self, "Sequence Gate",
                        "Structural design is not finalized.\nComplete pavement design before mix design."
                    )
                    return
                else:
                    QMessageBox.warning(
                        self, "Sequence Gate Warning",
                        "Warning: Structural design is not finalized.\nProceeding in decision-support mode for migrated project."
                    )

            self.inputs.set_project(self._current_project_id, self.db)
            self._show_page("inputs")

        # Gate 2: IITPAVE Verification requires layer configuration
        elif key == "iitpave_status":
            has_layers = (
                self.db.latest_structural_design(self._current_project_id) is not None
                or self.db.latest_stabilized_design(self._current_project_id) is not None
            )
            if status.get("structural") != "complete" and status.get("stabilized") != "complete":
                if not is_legacy:
                    QMessageBox.warning(
                        self, "Sequence Gate",
                        "Layer configuration required before verification."
                    )
                    return
                else:
                    if not has_layers:
                        QMessageBox.warning(
                            self, "Sequence Gate",
                            "Layer configuration required before verification (no design data exists)."
                        )
                        return
                    else:
                        QMessageBox.warning(
                            self, "Sequence Gate Warning",
                            "Warning: Layer configuration is not marked completed.\nProceeding since design data exists."
                        )

            self.iitpave_status.refresh()
            self._show_page("iitpave_status")

        elif key == "subgrade":
            self.subgrade.set_project(self._current_project_id, p.work_name)
            self._show_page("subgrade")

        elif key == "engineering_review":
            self.engineering_review.set_project(self._current_project_id, p.work_name)
            self._show_page("engineering_review")

        elif key == "submission":
            self.submission.set_project(self._current_project_id, p.work_name)
            self._show_page("submission")

        elif key == "reports":
            self._on_export_combined_report(self._current_project_id)

        elif key == "specs_admin":
            self.spec_admin.refresh()
            self._show_page("specs_admin")

        elif key == "structural":
            self.structural.set_project(self._current_project_id, p.work_name)
            self._show_page("structural")

        elif key == "stabilized":
            self.stabilized.set_project(self._current_project_id, p.work_name)
            self._show_page("stabilized")

        elif key == "maintenance":
            self.maintenance.set_project(self._current_project_id, p.work_name)
            self._show_page("maintenance")

        elif key == "material_qty":
            self.material_qty.set_project(self._current_project_id, p.work_name)
            self._show_page("material_qty")

        elif key == "condition":
            self.condition.set_project(self._current_project_id, p.work_name)
            self._show_page("condition")

        elif key == "traffic":
            self.traffic.set_project(self._current_project_id, p.work_name)
            self._show_page("traffic")

        elif key == "project":
            self.project_form.load_project(self._current_project_id)
            self._show_page("project")
        else:
            QMessageBox.information(
                self, "Coming soon",
                f"The '{key}' module is part of a later phase.\n"
                "Phase 1 wires the hub; engine + UI for this module arrive in a later phase."
            )

    def _on_structural_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Structural design saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_stabilized_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Stabilized pavement design saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_maintenance_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Maintenance design saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_traffic_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Traffic analysis saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_material_qty_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Material-quantity BOQ saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_condition_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Pavement condition survey saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    # ----- Phase 6 export handlers --------------------------------------

    def _project_meta_for_report(self, project_id: int) -> dict:
        """Common project metadata block for all report builders."""
        p = self.db.get_project(project_id)
        if p is None:
            return {}
        return dict(
            project_title=p.work_name or "",
            work_name=p.work_name or "",
            work_order_no=p.work_order_no or "",
            work_order_date=p.work_order_date or "",
            client=(p.client.name if p.client else ""),
            agency=p.agency or "",
            submitted_by=p.submitted_by or "",
        )

    def _on_export_structural(self, project_id: int) -> None:
        from app.reports.report_builder import _rehydrate_structural
        sd_row = self.db.latest_structural_design(project_id)
        result = _rehydrate_structural(
            sd_row,
            self.db.latest_mechanistic_validation(project_id),
        )
        if result is None:
            QMessageBox.information(
                self, "Nothing to export",
                "Save a structural design first.")
            return
        default = REPORTS_DIR / f"Structural_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Structural Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = StructuralReportContext(**meta)
            out = build_structural_docx(Path(path), ctx, result)
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Structural Word saved: {out}")
        except Exception as e:
            log.exception("Structural export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_stabilized(self, project_id: int) -> None:
        from app.reports.report_builder import _rehydrate_stabilized
        stab_row = self.db.latest_stabilized_design(project_id)
        mech_val = self.db.latest_mechanistic_validation(project_id)
        has_mechanistic = mech_val is not None and not mech_val.refused
        result = _rehydrate_stabilized(
            stab_row,
            has_mechanistic=has_mechanistic,
        )
        if result is None:
            QMessageBox.information(
                self, "Nothing to export",
                "Save a stabilized design first.")
            return
        default = REPORTS_DIR / f"Stabilized_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Stabilized Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = StabilizedReportContext(**meta)
            out = build_stabilized_docx(Path(path), ctx, result)
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Stabilized Word saved: {out}")
        except Exception as e:
            log.exception("Stabilized export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_maintenance(self, project_id: int) -> None:
        from app.reports.report_builder import (
            _rehydrate_cold_mix,
            _rehydrate_micro,
            _rehydrate_overlay,
        )
        ov = _rehydrate_overlay(self.db.latest_maintenance_design(project_id, "overlay"))
        cm = _rehydrate_cold_mix(self.db.latest_maintenance_design(project_id, "cold_mix"))
        ms = _rehydrate_micro(self.db.latest_maintenance_design(project_id, "micro_surfacing"))
        if not any((ov, cm, ms)):
            QMessageBox.information(
                self, "Nothing to export",
                "Save at least one maintenance sub-module first.")
            return
        default = REPORTS_DIR / f"Maintenance_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Maintenance Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = MaintenanceReportContext(**meta)
            out = build_maintenance_docx(
                Path(path), ctx,
                overlay=ov, cold_mix=cm, micro_surfacing=ms,
            )
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Maintenance Word saved: {out}")
        except Exception as e:
            log.exception("Maintenance export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_traffic(self, project_id: int) -> None:
        from app.reports.report_builder import _rehydrate_traffic
        row = self.db.latest_traffic_analysis(project_id)
        result = _rehydrate_traffic(row)
        if result is None:
            QMessageBox.information(self, "Nothing to export",
                "Save a traffic analysis first.")
            return
        default = REPORTS_DIR / f"Traffic_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Traffic Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = TrafficReportContext(**meta)
            out = build_traffic_docx(Path(path), ctx, result)
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Traffic Word saved: {out}")
        except Exception as e:
            log.exception("Traffic export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_condition(self, project_id: int) -> None:
        from app.reports.report_builder import _rehydrate_condition
        row = self.db.latest_condition_survey(project_id)
        result = _rehydrate_condition(row)
        if result is None:
            QMessageBox.information(self, "Nothing to export",
                "Save a pavement condition survey first.")
            return
        default = REPORTS_DIR / f"ConditionSurvey_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Condition-Survey Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = ConditionReportContext(**meta)
            out = build_condition_docx(Path(path), ctx, result)
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Condition Word saved: {out}")
        except Exception as e:
            log.exception("Condition export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_material_qty(self, project_id: int) -> None:
        from app.reports.report_builder import _rehydrate_material_qty
        row = self.db.latest_material_quantity(project_id)
        result = _rehydrate_material_qty(row)
        if result is None:
            QMessageBox.information(
                self, "Nothing to export",
                "Save a material-quantity BOQ first.")
            return
        default = REPORTS_DIR / f"MaterialQty_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Material-Quantity Word Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            ctx = MaterialQuantityReportContext(**meta)
            out = build_material_quantity_docx(Path(path), ctx, result)
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Material-quantity Word saved: {out}")
        except Exception as e:
            log.exception("Material-qty export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_material_excel(self, project_id: int) -> None:
        from app.reports.excel_exporter import build_boq_excel
        row = self.db.latest_material_quantity(project_id)
        if row is None:
            QMessageBox.information(
                self, "Nothing to export",
                "Save a material-quantity BOQ first.")
            return
        default = REPORTS_DIR / f"Preliminary_Estimate_BOQ_{project_id}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Preliminary Estimate BOQ Spreadsheet",
            str(default), "Excel Workbook (*.xlsx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            out = build_boq_excel(Path(path), project_id, self.db, meta)
            QMessageBox.information(self, "Spreadsheet exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Preliminary Estimate BOQ Excel saved: {out}")
        except Exception as e:
            log.exception("Excel export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _select_iitpave_schema_history_for_report(
        self,
        project_id: int,
    ) -> tuple[bool, tuple[int, ...] | None]:
        rows = self.db.list_iitpave_schema_diagnostics(project_id)
        review = build_iitpave_schema_history_review(project_id, rows)
        if not review.items:
            return True, None

        dlg = QDialog(self)
        dlg.setWindowTitle("Select IITPAVE schema history")
        dlg.resize(620, 420)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "Select persisted IITPAVE schema diagnostics history records to "
            "include in the combined report."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        selector = QListWidget()
        for item in review.items:
            row = QListWidgetItem(item.label, selector)
            row.setData(Qt.UserRole, item.id)
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            row.setCheckState(Qt.Checked)
        layout.addWidget(selector, stretch=1)

        note = QLabel("Selection is audit-only; engineering calculations remain blocked.")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return False, None

        selected: list[int] = []
        for idx in range(selector.count()):
            row = selector.item(idx)
            if row.checkState() == Qt.Checked:
                selected.append(int(row.data(Qt.UserRole)))
        return True, tuple(selected)

    def _on_export_combined_report(self, project_id: int) -> None:
        """Hub 'Reports' tile — module-aware combined Word output."""
        default = REPORTS_DIR / f"PavementReport_{project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Combined Pavement-Design Report",
            str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            meta = self._project_meta_for_report(project_id)
            p = self.db.get_project(project_id)
            ctx = CombinedReportContext(
                **meta,
                binder_grade=(p.binder_grade if (p and p.binder_grade) else ""),
                mix_type_key=(p.mix_type if (p and p.mix_type) else ""),
            )
            ok, schema_history_ids = self._select_iitpave_schema_history_for_report(
                project_id
            )
            if not ok:
                return
            # Pass live mix-design only if it belongs to this project
            mix_live = None
            chart_set = None
            mat_calc = None
            if (self._last_result is not None
                    and self._current_project_id == project_id):
                mix_live = self._last_result
                chart_set = self._last_chart_set
                mat_calc = self._last_material_calc
            out, included = build_combined_report(
                Path(path), self.db, project_id, ctx,
                mix_result_live=mix_live,
                mix_chart_set=chart_set,
                mix_material_calc=mat_calc,
                schema_history_selection_ids=schema_history_ids,
            )
            QMessageBox.information(
                self, "Combined report exported",
                "Saved to:\n" + str(out)
                + "\n\nSections included:\n - "
                + "\n - ".join(included)
            )
            self.statusBar().showMessage(f"Combined Word saved: {out}")
        except ValueError as e:
            QMessageBox.information(self, "Nothing to export", str(e))
        except Exception as e:
            log.exception("Combined report failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_delete_project(self, project_id: int) -> None:
        ok = self.db.delete_project(project_id)
        if ok:
            self.statusBar().showMessage(f"Project #{project_id} deleted.")
            if self._current_project_id == project_id:
                self._current_project_id = None
                self._last_result = None
                self._last_material_calc = None
            self.dashboard.refresh()
            self._show_page("dashboard")
        else:
            QMessageBox.warning(self, "Delete failed",
                                f"Project #{project_id} could not be deleted.")

    # ----- Phase 21 project exchange UI --------------------------------

    def _project_exchange_issue_text(self, issues) -> str:
        if not issues:
            return ""
        lines = []
        for issue in issues:
            if isinstance(issue, dict):
                severity = str(issue.get("severity") or "warning")
                field_name = str(issue.get("field") or "")
                message = str(issue.get("message") or "")
            else:
                severity = str(issue.severity)
                field_name = str(issue.field or "")
                message = str(issue.message)
            prefix = severity.upper()
            field = f" ({field_name})" if field_name else ""
            lines.append(f"{prefix}{field}: {message}")
        return "\n".join(lines)

    def _on_export_project(self, project_id: int) -> None:
        p = self.db.get_project(project_id)
        if p is None:
            QMessageBox.warning(
                self, "Export failed", f"Project #{project_id} was not found."
            )
            return
        safe_name = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in (p.work_name or f"Project_{project_id}")
        ).strip("_") or f"Project_{project_id}"
        default = REPORTS_DIR / f"{safe_name}_project_export.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project Export",
            str(default),
            "SamPave Project Export (*.json);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            payload = export_project(self.db, project_id)
            out = write_project_export(payload, Path(path))
            issue_text = self._project_exchange_issue_text(
                payload.get("validation", {}).get("issues", ())
            )
            msg = f"Project export saved to:\n{out}"
            if issue_text:
                msg += f"\n\nValidation notes:\n{issue_text}"
            QMessageBox.information(self, "Project exported", msg)
            self.statusBar().showMessage(f"Project export saved: {out}")
        except Exception as e:
            log.exception("Project export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_import_project_export(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project Export",
            "",
            "SamPave Project Export (*.json);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            payload = read_project_export(Path(path))
            result = import_project(self.db, payload)
            self._current_project_id = result.project_id
            self.project_form.load_project(result.project_id)
            self.dashboard.refresh()
            self._refresh_hub()
            self._show_page("hub")

            issue_text = self._project_exchange_issue_text(result.issues)
            msg = (
                f"Imported as project #{result.project_id}:\n"
                f"{result.work_name}"
            )
            if issue_text:
                msg += f"\n\nValidation notes:\n{issue_text}"
            QMessageBox.information(self, "Project imported", msg)
            self.statusBar().showMessage(
                f"Project import complete: #{result.project_id}"
            )
        except ProjectImportError as e:
            issue_text = self._project_exchange_issue_text(e.result.issues)
            QMessageBox.critical(
                self,
                "Import rejected",
                issue_text or str(e),
            )
        except Exception as e:
            log.exception("Project import failed")
            QMessageBox.critical(self, "Import failed", str(e))

    # ----- Phase 32 IITPAVE schema diagnostics workflow -----------------

    def _on_iitpave_schema_diagnostics(self) -> None:
        fixture_dir = QFileDialog.getExistingDirectory(
            self,
            "Select IITPAVE Fixture Folder",
            "",
        )
        if not fixture_dir:
            return

        default_name = "IITPAVE_Schema_Diagnostics"
        if self._current_project_id is not None:
            p = self.db.get_project(self._current_project_id)
            if p and p.work_name:
                default_name = "".join(
                    ch if ch.isalnum() or ch in ("-", "_") else "_"
                    for ch in p.work_name
                ).strip("_") or default_name
        default = REPORTS_DIR / f"{default_name}_schema_diagnostics.docx"
        report_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save IITPAVE Schema Diagnostics Report",
            str(default),
            "Word Document (*.docx)",
        )
        if not report_path:
            return

        try:
            meta = (
                self._project_meta_for_report(self._current_project_id)
                if self._current_project_id is not None
                else {}
            )
            ctx = IITPaveSchemaReportContext(**meta)
            result = run_iitpave_schema_diagnostics_workflow(
                Path(fixture_dir),
                report_path=Path(report_path),
                context=ctx,
            )
            history_row = None
            if self._current_project_id is not None:
                history_row = self.db.save_iitpave_schema_diagnostics(
                    project_id=self._current_project_id,
                    result=result,
                )
            QMessageBox.information(
                self,
                "IITPAVE schema diagnostics",
                result.operator_message,
            )
            if result.report_written:
                msg = f"IITPAVE schema diagnostics saved: {result.report_path}"
            else:
                msg = "IITPAVE schema diagnostics summary generated; report not written."
            if history_row is not None:
                msg = f"{msg} History #{history_row.id} recorded."
            self.statusBar().showMessage(msg)
        except Exception as e:
            log.exception("IITPAVE schema diagnostics failed")
            QMessageBox.critical(self, "Schema diagnostics failed", str(e))

    def _build_iitpave_schema_history_dialog(self, review):
        dlg = QDialog(self)
        dlg.setWindowTitle("IITPAVE schema diagnostics history")
        dlg.resize(760, 520)
        layout = QVBoxLayout(dlg)

        summary = QLabel("\n".join(review.operator_summary))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        selector = QListWidget()
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(260)
        layout.addWidget(selector)
        layout.addWidget(detail, stretch=1)

        by_id = {item.id: item for item in review.items}
        for item in review.items:
            row = QListWidgetItem(item.label, selector)
            row.setData(Qt.UserRole, item.id)

        def _show_item(current, _previous=None):
            if current is None:
                detail.setPlainText("")
                return
            item = by_id.get(current.data(Qt.UserRole))
            detail.setPlainText(
                format_iitpave_schema_history_item_text(item) if item else ""
            )

        selector.currentItemChanged.connect(_show_item)
        if selector.count():
            selector.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        return dlg

    def _on_iitpave_schema_history(self) -> None:
        if self._current_project_id is None:
            QMessageBox.warning(
                self,
                "IITPAVE schema history",
                "Select or create a project before reviewing schema diagnostics history.",
            )
            return

        try:
            rows = self.db.list_iitpave_schema_diagnostics(self._current_project_id)
            review = build_iitpave_schema_history_review(self._current_project_id, rows)
            if not review.items:
                QMessageBox.information(
                    self,
                    "IITPAVE schema history",
                    "\n".join(review.operator_summary),
                )
                self.statusBar().showMessage("No IITPAVE schema diagnostics history found.")
                return
            dlg = self._build_iitpave_schema_history_dialog(review)
            self.statusBar().showMessage(
                f"IITPAVE schema diagnostics history loaded: {review.item_count} record(s)."
            )
            dlg.exec()
        except Exception as e:
            log.exception("IITPAVE schema history review failed")
            QMessageBox.critical(self, "Schema history failed", str(e))

    def _build_iitpave_schema_report_audit_dialog(self, review):
        dlg = QDialog(self)
        dlg.setWindowTitle("IITPAVE schema-history report audit")
        dlg.resize(780, 540)
        layout = QVBoxLayout(dlg)

        summary = QLabel("\n".join(review.operator_summary))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        selector = QListWidget()
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(280)
        layout.addWidget(selector)
        layout.addWidget(detail, stretch=1)

        by_id = {item.id: item for item in review.items}
        for item in review.items:
            row = QListWidgetItem(item.label, selector)
            row.setData(Qt.UserRole, item.id)

        def _show_item(current, _previous=None):
            if current is None:
                detail.setPlainText("")
                return
            item = by_id.get(current.data(Qt.UserRole))
            detail.setPlainText(
                format_iitpave_schema_history_selection_audit_item_text(item)
                if item else ""
            )

        selector.currentItemChanged.connect(_show_item)
        if selector.count():
            selector.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        return dlg

    def _on_iitpave_schema_report_audit(self) -> None:
        if self._current_project_id is None:
            QMessageBox.warning(
                self,
                "IITPAVE report audit",
                "Select or create a project before reviewing schema-history report audits.",
            )
            return

        try:
            rows = self.db.list_iitpave_schema_history_selection_audits(
                self._current_project_id
            )
            review = build_iitpave_schema_history_selection_audit_review(
                self._current_project_id,
                rows,
            )
            if not review.items:
                QMessageBox.information(
                    self,
                    "IITPAVE report audit",
                    "\n".join(review.operator_summary),
                )
                self.statusBar().showMessage(
                    "No IITPAVE schema-history report audit records found."
                )
                return
            dlg = self._build_iitpave_schema_report_audit_dialog(review)
            self.statusBar().showMessage(
                "IITPAVE schema-history report audit loaded: "
                f"{review.item_count} record(s)."
            )
            dlg.exec()
        except Exception as e:
            log.exception("IITPAVE report audit review failed")
            QMessageBox.critical(self, "Report audit failed", str(e))

    def _build_report_revisions_dialog(self, review):
        dlg = QDialog(self)
        dlg.setWindowTitle("Report revision snapshots")
        dlg.resize(780, 540)
        layout = QVBoxLayout(dlg)

        summary = QLabel("\n".join(review.operator_summary))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        selector = QListWidget()
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(280)
        layout.addWidget(selector)
        layout.addWidget(detail, stretch=1)

        by_label = {item.revision_label: item for item in review.items}
        for item in review.items:
            row = QListWidgetItem(
                f"{item.revision_label or 'Revision'} | {item.generated_at} | "
                f"{item.fingerprint_short}",
                selector,
            )
            row.setData(Qt.UserRole, item.revision_label)

        def _show_item(current, _previous=None):
            if current is None:
                detail.setPlainText("")
                return
            item = by_label.get(current.data(Qt.UserRole))
            detail.setPlainText(format_report_revision_snapshot_text(item) if item else "")

        selector.currentItemChanged.connect(_show_item)
        if selector.count():
            selector.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        return dlg

    def _on_report_revisions(self) -> None:
        if self._current_project_id is None:
            QMessageBox.warning(
                self,
                "Report revisions",
                "Select or create a project before reviewing report revisions.",
            )
            return

        try:
            rows = self.db.list_report_revision_snapshots(self._current_project_id)
            review = build_report_revision_history_review(
                self._current_project_id,
                rows,
            )
            if not review.items:
                QMessageBox.information(
                    self,
                    "Report revisions",
                    "\n".join(review.operator_summary),
                )
                self.statusBar().showMessage("No report revision snapshots found.")
                return
            dlg = self._build_report_revisions_dialog(review)
            self.statusBar().showMessage(
                f"Report revision snapshots loaded: {review.item_count} record(s)."
            )
            dlg.exec()
        except Exception as e:
            log.exception("Report revision review failed")
            QMessageBox.critical(self, "Report revisions failed", str(e))

    def _build_deployment_diagnostics_dialog(self, checklist):
        dlg = QDialog(self)
        dlg.setWindowTitle("Deployment diagnostics")
        dlg.resize(800, 560)
        layout = QVBoxLayout(dlg)

        summary = QLabel("\n".join(checklist.operator_summary))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        selector = QListWidget()
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(300)
        layout.addWidget(selector)
        layout.addWidget(detail, stretch=1)

        by_key = {item.key: item for item in checklist.items}
        for item in checklist.items:
            row = QListWidgetItem(item.operator_line, selector)
            row.setData(Qt.UserRole, item.key)

        def _show_item(current, _previous=None):
            if current is None:
                detail.setPlainText("")
                return
            item = by_key.get(current.data(Qt.UserRole))
            detail.setPlainText(format_deployment_checklist_item_text(item) if item else "")

        selector.currentItemChanged.connect(_show_item)
        if selector.count():
            selector.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        return dlg

    def _on_deployment_diagnostics(self) -> None:
        try:
            checklist = build_deployment_packaging_checklist(
                include_installer_preparation=True,
            )
            dlg = self._build_deployment_diagnostics_dialog(checklist)
            self.statusBar().showMessage(
                f"Deployment diagnostics loaded: {len(checklist.items)} check(s), "
                f"status {checklist.status}."
            )
            dlg.exec()
        except Exception as e:
            log.exception("Deployment diagnostics review failed")
            QMessageBox.critical(self, "Deployment diagnostics failed", str(e))

    # ----- compute -----

    def _on_reset_inputs(self) -> None:
        # Re-instantiate the inputs panel (cheapest way to reset to blank lab fields)
        old = self.inputs
        new = InputsPanel()
        new.compute_requested.connect(self._on_compute)
        new.reset_requested.connect(self._on_reset_inputs)
        idx = self._page_keys["inputs"]
        self.stack.removeWidget(old)
        self.stack.insertWidget(idx, new)
        old.deleteLater()
        self.inputs = new
        # F1 wire-up: re-apply mix-type-driven standards envelope after reset,
        # while leaving operator-entered lab-data fields blank.
        if self._current_project_id is not None:
            self.inputs.set_project(self._current_project_id, self.db)
        self._show_page("inputs")

    def _on_compute(self) -> None:
        if self._current_project_id is None:
            QMessageBox.warning(self, "No project",
                                "Please create or open a project first.")
            self._show_page("project")
            return
        try:
            # At the beginning of _on_compute, extract from self.inputs:
            mix_type = self.inputs.mix_type.currentData()
            binder_grade = self.inputs.binder_grade.currentData()
            binder_props = self.inputs._binder_props
            
            # Save to db so downstream calculations see the updated values
            import json
            self.db.update_project(
                self._current_project_id,
                mix_type=mix_type,
                binder_grade=binder_grade,
                binder_properties_json=json.dumps(binder_props)
            )

            payload = self.inputs.collect_all()
            coarse, fine, bit = payload["spgr"]
            # bitumen SG for GmmInput requires the value — let engine compute it
            gmm_in = payload["gmm"]

            grad = payload["gradation"]

            p = self.db.get_project(self._current_project_id)
            # F4: refuse to compute without an explicit mix type.
            if not p or not p.mix_type:
                QMessageBox.warning(
                    self, "Mix type required",
                    "This project has no Mix Type set. Please pick one in "
                    "the Mix Design panel before computing."
                )
                self._show_page("inputs")
                return
            mix_type = p.mix_type
            proj = ProjectInfo(
                mix_type=mix_type,
                work_name=p.work_name if p else "",
                client=p.client.name if (p and p.client) else "",
                materials={name: "" for name in grad.blend_ratios},
            )
            inp = MixDesignInput(
                project=proj,
                gradation=grad,
                sg_coarse=coarse,
                sg_fine=fine,
                sg_bitumen=bit,
                gmb=payload["gmb"],
                gmm=gmm_in,
                stability_flow=payload["stability_flow"],
            )
            result = compute_mix_design(inp)
            mat_result = compute_material_calc(payload["material_calc"])
            self._last_result = result
            self._last_material_calc = mat_result
            self._last_inputs_payload = payload
            self._last_chart_set = build_chart_set(result.summary, result.obc)

            self.db.save_mix_design(
                project_id=self._current_project_id,
                inputs_payload={
                    "gradation": grad,
                    "spgr": {"coarse": list(coarse.keys()), "fine": list(fine.keys())},
                    "gmb": payload["gmb"],
                    "gmm": gmm_in,
                    "stability_flow": payload["stability_flow"],
                    "materials": {},
                },
                result=result,
            )
            # F2 wire-up: tell the results panel which mix type this result
            # belongs to, so the placeholder warning banner can surface.
            self.results.set_mix_type_key(mix_type)
            self.results.set_result(result, mat_result)
            self.db.set_module_status(self._current_project_id, "mix_design", "complete")
            self._refresh_hub()
            self._show_page("results")
            self.statusBar().showMessage(
                f"Computed. OBC = {result.obc.obc_pct:.2f}%  •  "
                f"{result.compliance.spec_name}: "
                f"{'PASS' if result.compliance.overall_pass else 'FAIL'}"
            )
            self.dashboard.refresh()
        except Exception as e:
            log.exception("Compute failed")
            QMessageBox.critical(
                self, "Computation error",
                f"{e}\n\n{traceback.format_exc()}"
            )

    # ----- export -----

    def _ensure_result(self) -> bool:
        if not self._last_result:
            QMessageBox.warning(self, "No result", "Compute the mix design first.")
            return False
        return True

    def _build_report_context(self) -> ReportContext:
        import json as _json
        p = self.db.get_project(self._current_project_id) if self._current_project_id else None
        binder_props: dict = {}
        if p and p.binder_properties_json:
            try:
                binder_props = _json.loads(p.binder_properties_json)
            except _json.JSONDecodeError:
                binder_props = {}
        # F4: do not silently default to DBM-II. Pass through the project's
        # actual mix_type; callers requiring a non-empty value validate
        # before reaching here (compute path + hub guard).
        return ReportContext(
            project_title=(p.work_name if p else "") or "Mix Design",
            mix_type_key=(p.mix_type if (p and p.mix_type) else ""),
            work_name=p.work_name if p else "",
            work_order_no=p.work_order_no if p else "",
            work_order_date=p.work_order_date if p else "",
            client=(p.client.name if (p and p.client) else ""),
            agency=p.agency if p else "",
            submitted_by=p.submitted_by if p else "",
            materials={},
            binder_grade=(p.binder_grade if (p and p.binder_grade) else ""),
            binder_properties=binder_props,
        )

    def _on_export_word(self) -> None:
        if not self._ensure_result():
            return
        default = REPORTS_DIR / f"MixDesign_{self._current_project_id}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Word Report", str(default), "Word Document (*.docx)"
        )
        if not path:
            return
        try:
            ctx = self._build_report_context()
            out = build_mix_design_docx(Path(path), ctx, self._last_result,
                                        self._last_chart_set,
                                        material_calc=self._last_material_calc)
            md = self.db.latest_mix_design(self._current_project_id)
            if md:
                self.db.record_report(mix_design_id=md.id,
                                      file_path=str(out), file_type="docx")
            QMessageBox.information(self, "Report exported", f"Saved to:\n{out}")
            self.statusBar().showMessage(f"Word saved: {out}")
        except Exception as e:
            log.exception("Word export failed")
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_import_summary(self) -> None:
        """Import a pre-computed Marshall summary Excel and show results."""
        from app.core import MIX_SPECS, MIX_TYPES

        # 1. File picker
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Marshall Summary Excel", "",
            "Excel Files (*.xlsx *.xls *.xlsm);;All Files (*)"
        )
        if not path:
            return

        # 2. Mix-type picker dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Mix Type")
        dlg.setMinimumWidth(320)
        form = QFormLayout(dlg)
        form.setContentsMargins(16, 12, 16, 12)
        form.setSpacing(10)

        combo = QComboBox()
        for key, spec in MIX_SPECS.items():
            combo.addItem(f"{key}  —  {spec.name}", key)
        # F4: default selection is the first *verified* MIX_SPECS entry, not
        # the hardcoded literal "DBM-II". Falls back to the first available
        # entry if none are marked verified.
        default_key = next(
            (k for k in MIX_SPECS.keys()
             if (MIX_TYPES.get(k) and (MIX_TYPES[k].status or "").strip() == "verified")),
            next(iter(MIX_SPECS.keys()), None),
        )
        idx = combo.findData(default_key) if default_key else -1
        if idx >= 0:
            combo.setCurrentIndex(idx)
        form.addRow("Mix Type / Spec:", combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        mix_type_key = combo.currentData()

        # 3. Parse and compute
        try:
            imported = parse_summary_excel(path, mix_type_key=mix_type_key)
        except Exception as e:
            log.exception("Import summary failed")
            QMessageBox.critical(
                self, "Import failed",
                f"Could not read the Excel file:\n\n{e}"
            )
            return

        # 4. Store as last result (no project ID required for imports)
        from app.graphs import build_chart_set
        self._last_result = imported
        self._last_material_calc = None
        self._last_inputs_payload = None
        self._last_chart_set = build_chart_set(imported.summary, imported.obc)

        # F2 wire-up for imported results too
        self.results.set_mix_type_key(mix_type_key)
        self.results.set_result(imported)
        self._show_page("results")
        self.statusBar().showMessage(
            f"Imported: {Path(path).name}  •  OBC = {imported.obc.obc_pct:.2f}%  •  "
            f"{imported.compliance.spec_name}: "
            f"{'PASS' if imported.compliance.overall_pass else 'FAIL'}"
        )

    def _on_export_pdf(self) -> None:
        if not self._ensure_result():
            return
        default_docx = REPORTS_DIR / f"MixDesign_{self._current_project_id}.docx"
        try:
            ctx = self._build_report_context()
            docx_path = build_mix_design_docx(default_docx, ctx, self._last_result,
                                              self._last_chart_set,
                                              material_calc=self._last_material_calc)
            pdf_path = export_to_pdf(docx_path)
            md = self.db.latest_mix_design(self._current_project_id)
            if md:
                self.db.record_report(mix_design_id=md.id,
                                      file_path=str(pdf_path), file_type="pdf")
            QMessageBox.information(self, "PDF exported", f"Saved to:\n{pdf_path}")
            self.statusBar().showMessage(f"PDF saved: {pdf_path}")
        except Exception as e:
            log.exception("PDF export failed")
            QMessageBox.critical(self, "Export failed", str(e))
