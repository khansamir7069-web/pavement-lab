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
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __version__
from app.config import REPORTS_DIR
from app.core import compute_material_calc, compute_mix_design
from app.core.import_summary import ImportedMixResult, parse_summary_excel
from app.core.models import MixDesignInput, ProjectInfo
from app.db import get_db
from app.graphs import build_chart_set
from app.reports import (
    CombinedReportContext,
    MaintenanceReportContext,
    MaterialQuantityReportContext,
    ReportContext,
    StructuralReportContext,
    build_combined_report,
    build_maintenance_docx,
    build_material_quantity_docx,
    build_mix_design_docx,
    build_structural_docx,
)
from app.reports.word_report import export_to_pdf

from .widgets.common import Card
from .widgets.dashboard import Dashboard
from .widgets.inputs_panel import InputsPanel
from .widgets.maintenance_panel import MaintenancePanel
from .widgets.material_qty_panel import MaterialQuantityPanel
from .widgets.module_hub import ModuleHub
from .widgets.project_form import ProjectForm
from .widgets.results_panel import ResultsPanel
from .widgets.spec_admin import SpecAdminPanel
from .widgets.structural_panel import StructuralPanel


log = logging.getLogger(__name__)


SIDEBAR_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Project", "project"),
    ("Module Hub", "hub"),
    ("Mix Design Inputs", "inputs"),
    ("Structural Design", "structural"),
    ("Maintenance", "maintenance"),
    ("Material Quantity", "material_qty"),
    ("Results & Report", "results"),
    ("Specifications", "specs_admin"),
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

        # Import button at bottom of sidebar
        self.btn_import = QPushButton("⬆  Import Summary Excel")
        self.btn_import.setObjectName("ImportBtn")
        self.btn_import.setToolTip(
            "Load a pre-computed Marshall summary table from an Excel file\n"
            "(Pb %, Gmm, Gmb, VIM, VMA, VFB, Stability, Flow, MQ)."
        )
        self.btn_import.clicked.connect(self._on_import_summary)
        sb_layout.addWidget(self.btn_import)

        version_lbl = QLabel(f"v{__version__}")
        version_lbl.setObjectName("SidebarTag")
        version_lbl.setAlignment(Qt.AlignCenter)
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
        self.maintenance = MaintenancePanel(self.db)
        self.material_qty = MaterialQuantityPanel(self.db)

        # Wire Back buttons on every page's header.
        # Lambdas must swallow Qt's clicked(bool) positional arg with *_.
        from .widgets.common import PageHeader
        back_routes = (
            (self.project_form, "dashboard"),
            (self.inputs,       "hub"),
            (self.results,      "hub"),
            (self.spec_admin,   "hub"),
            (self.structural,   "hub"),
            (self.maintenance,  "hub"),
            (self.material_qty, "hub"),
        )
        for w, target in back_routes:
            hdr = w.findChild(PageHeader)
            if hdr is not None:
                hdr.enable_back(lambda *_, t=target: self._show_page(t))

        self._page_keys: dict[str, int] = {}
        for label, key in SIDEBAR_ITEMS:
            widget = {
                "dashboard": self.dashboard,
                "project": self.project_form,
                "hub": self.hub,
                "inputs": self.inputs,
                "results": self.results,
                "specs_admin": self.spec_admin,
                "structural": self.structural,
                "maintenance": self.maintenance,
                "material_qty": self.material_qty,
            }[key]
            idx = self.stack.addWidget(widget)
            self._page_keys[key] = idx

        # Status
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"{__app_name__} ready  •  DB: {self.db.path}")

    def _wire_signals(self) -> None:
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.dashboard.new_project.connect(self._on_new_project)
        self.dashboard.open_project.connect(self._on_open_project)
        self.dashboard.delete_project.connect(self._on_delete_project)
        self.project_form.saved.connect(self._on_project_saved)
        self.hub.module_selected.connect(self._on_module_selected)
        self.structural.saved.connect(self._on_structural_saved)
        self.structural.export_requested.connect(self._on_export_structural)
        self.maintenance.saved.connect(self._on_maintenance_saved)
        self.maintenance.export_requested.connect(self._on_export_maintenance)
        self.material_qty.saved.connect(self._on_material_qty_saved)
        self.material_qty.export_requested.connect(self._on_export_material_qty)
        self.inputs.compute_requested.connect(self._on_compute)
        self.inputs.load_demo_requested.connect(self._on_load_demo)
        self.results.generate_word.connect(self._on_export_word)
        self.results.generate_pdf.connect(self._on_export_pdf)

    # ----- navigation -----

    def _show_page(self, key: str) -> None:
        idx = self._page_keys[key]
        self.stack.setCurrentIndex(idx)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav.item(row).data(Qt.UserRole)
        self.stack.setCurrentIndex(self._page_keys[key])
        if key == "dashboard":
            self.dashboard.refresh()

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
        """Route user from Hub into the chosen module."""
        if key == "mix_design":
            if self._current_project_id is None:
                QMessageBox.warning(self, "No project", "Please save a project first.")
                self._show_page("project")
                return
            # Ensure project has a mix_type — if not, force user back to project form.
            p = self.db.get_project(self._current_project_id)
            if not p or not p.mix_type:
                QMessageBox.information(
                    self, "Mix type required",
                    "This project has no Mix Type set. Please pick one in the Project form."
                )
                self._show_page("project")
                return
            self._show_page("inputs")
        elif key == "reports":
            if self._current_project_id is None:
                QMessageBox.warning(self, "No project",
                                    "Please save a project first.")
                self._show_page("project")
                return
            self._on_export_combined_report(self._current_project_id)
        elif key == "specs_admin":
            # Spec admin needs no project — opens directly
            self.spec_admin.refresh()
            self._show_page("specs_admin")
        elif key == "structural":
            if self._current_project_id is None:
                QMessageBox.warning(self, "No project",
                                    "Please save a project first.")
                self._show_page("project")
                return
            p = self.db.get_project(self._current_project_id)
            self.structural.set_project(
                self._current_project_id, p.work_name if p else ""
            )
            self._show_page("structural")
        elif key == "maintenance":
            if self._current_project_id is None:
                QMessageBox.warning(self, "No project",
                                    "Please save a project first.")
                self._show_page("project")
                return
            p = self.db.get_project(self._current_project_id)
            self.maintenance.set_project(
                self._current_project_id, p.work_name if p else ""
            )
            self._show_page("maintenance")
        elif key == "material_qty":
            if self._current_project_id is None:
                QMessageBox.warning(self, "No project",
                                    "Please save a project first.")
                self._show_page("project")
                return
            p = self.db.get_project(self._current_project_id)
            self.material_qty.set_project(
                self._current_project_id, p.work_name if p else ""
            )
            self._show_page("material_qty")
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

    def _on_maintenance_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Maintenance design saved for project #{project_id}."
        )
        self._refresh_hub()
        self.dashboard.refresh()

    def _on_material_qty_saved(self, project_id: int) -> None:
        self.statusBar().showMessage(
            f"Material-quantity BOQ saved for project #{project_id}."
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
        result = _rehydrate_structural(sd_row)
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

    # ----- compute -----

    def _on_load_demo(self) -> None:
        # Re-instantiate the inputs panel (cheapest way to reset)
        old = self.inputs
        new = InputsPanel()
        new.compute_requested.connect(self._on_compute)
        new.load_demo_requested.connect(self._on_load_demo)
        idx = self._page_keys["inputs"]
        self.stack.removeWidget(old)
        self.stack.insertWidget(idx, new)
        old.deleteLater()
        self.inputs = new
        self._show_page("inputs")

    def _on_compute(self) -> None:
        if self._current_project_id is None:
            QMessageBox.warning(self, "No project",
                                "Please create or open a project first.")
            self._show_page("project")
            return
        try:
            payload = self.inputs.collect_all()
            coarse, fine, bit = payload["spgr"]
            # bitumen SG for GmmInput requires the value — let engine compute it
            gmm_in = payload["gmm_tab"].collect(bitumen_sg=0.0)

            # Strip cement from blend so Gsb mirrors Excel behavior on the sample.
            # Users can re-include cement by editing the engine call directly.
            grad = payload["gradation"]
            grad_blend = {k: v for k, v in grad.blend_ratios.items() if k.lower() != "cement"}
            from app.core import GradationInput
            grad_for_gsb = GradationInput(
                sieve_sizes_mm=grad.sieve_sizes_mm,
                pass_pct=grad.pass_pct,
                blend_ratios=grad_blend,
                spec_lower=grad.spec_lower,
                spec_upper=grad.spec_upper,
            )

            p = self.db.get_project(self._current_project_id)
            mix_type = p.mix_type if p else "DBM-II"
            proj = ProjectInfo(
                mix_type=mix_type,
                work_name=p.work_name if p else "",
                client=p.client.name if (p and p.client) else "",
            )
            inp = MixDesignInput(
                project=proj,
                gradation=grad_for_gsb,
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
        return ReportContext(
            project_title=(p.work_name if p else "") or "Mix Design",
            mix_type_key=(p.mix_type if (p and p.mix_type) else "DBM-II"),
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
        from app.core import MIX_SPECS

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
        # Default to DBM-II
        idx = combo.findData("DBM-II")
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
