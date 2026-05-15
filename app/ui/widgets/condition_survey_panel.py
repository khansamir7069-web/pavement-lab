"""Pavement Condition Survey panel — Phase 10 + Phase 11 image wiring.

Independent panel mirroring TrafficPanel: metadata header + distress
table (add/remove rows) + Compute + Save + Export Word.

Phase 11 (additive): the previously stub-only ``image_paths`` reserved
field is now backed by a working image-evidence gallery that calls
``app.core.condition_survey.image_pipeline.attach_image`` / ``delete_evidence``.
The PCI engine still ignores ``image_paths``; only the storage + UI hook
is wired in this step. AI / GIS fields remain stub-only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import IMAGES_DIR
from app.core import (
    DISTRESS_TYPES,
    SEVERITY_LEVELS,
    ConditionSurveyInput,
    ConditionSurveyResult,
    DistressRecord,
    compute_condition_survey,
)
from app.core.condition_survey.image_pipeline import (
    attach_image,
    delete_evidence,
)
from .common import (
    Card,
    FutureExpansionBanner,
    InfoBanner,
    PageHeader,
    PlaceholderBanner,
    styled_button,
)
from .distress_images_dialog import DistressImagesDialog


def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(f" {suffix}")
    return sp


_DISTRESS_LABELS = {code: t.label for code, t in DISTRESS_TYPES.items()}
_DISTRESS_CODES = tuple(DISTRESS_TYPES.keys())

# Phase 11: pre-save attachments live under
# IMAGES_DIR / "condition" / <project_id> / <DRAFT_SURVEY_ID>. We don't
# migrate files when the survey row gets a real id; the relative path
# persisted on the survey continues to resolve.
DRAFT_SURVEY_ID: int = 0


def _open_in_file_browser(path: Path) -> None:
    """Best-effort OS-native folder open. Silent on failure."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


class ConditionSurveyPanel(QWidget):
    """Independent pavement condition survey page."""

    saved = Signal(int)
    export_requested = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last: ConditionSurveyResult | None = None
        # Phase 11: relative paths (POSIX, relative to IMAGES_DIR) of
        # images attached via the gallery. Source of truth for
        # ConditionSurveyInput.image_paths whenever non-empty; the
        # read-only ed_image_paths textarea acts only as a mirror.
        self._evidence: list[str] = []
        self._build()

    # ---------- UI build ----------------------------------------------------
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Pavement Condition Survey",
            "Distress recording + PCI score (ASTM D6433 shape; placeholder weights)"
        )
        self.btn_add = styled_button("Add Distress", "secondary")
        self.btn_add.clicked.connect(self._add_row)
        self.btn_remove = styled_button("Remove Selected", "secondary")
        self.btn_remove.clicked.connect(self._remove_row)
        self.btn_compute = styled_button("Compute PCI")
        self.btn_compute.clicked.connect(self._on_compute)
        self.btn_save = styled_button("Save", "secondary")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        self.btn_export = styled_button("Export Word", "secondary")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        for b in (self.btn_export, self.btn_save, self.btn_compute,
                  self.btn_remove, self.btn_add):
            self.header.add_action(b)
        lay.addWidget(self.header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(12)

        # Placeholder warning banner (always shown — weights uncalibrated)
        self.lbl_placeholder = PlaceholderBanner(
            "[PLACEHOLDER] PCI weights, severity multipliers and rehab "
            "recommendations are uncalibrated foundation values. Confirm "
            "against ASTM D6433 / IRC:82 before adopting any verdict."
        )
        bl.addWidget(self.lbl_placeholder)

        self.proj_banner = InfoBanner("")
        bl.addWidget(self.proj_banner)

        # ---- Survey metadata card ------------------------------------
        meta_card = Card()
        meta_form = QFormLayout(meta_card)
        meta_form.setContentsMargins(20, 16, 20, 16); meta_form.setSpacing(8)
        self.work_name = QLineEdit()
        self.surveyed_by = QLineEdit()
        self.survey_date = QLineEdit(); self.survey_date.setPlaceholderText("YYYY-MM-DD")
        self.lane_id = QLineEdit(); self.lane_id.setPlaceholderText("e.g. LHS / RHS / Lane 1")
        self.ch_from = _spin(0.0, 0, 10_000, 0.1, 3, "km")
        self.ch_to   = _spin(0.0, 0, 10_000, 0.1, 3, "km")
        meta_form.addRow("Name of Work", self.work_name)
        meta_form.addRow("Surveyed By", self.surveyed_by)
        meta_form.addRow("Survey Date", self.survey_date)
        meta_form.addRow("Lane / Carriageway", self.lane_id)
        meta_form.addRow("Chainage From", self.ch_from)
        meta_form.addRow("Chainage To", self.ch_to)
        bl.addWidget(meta_card)

        # ---- Distress table card --------------------------------------
        table_card = Card()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(20, 16, 20, 16); tl.setSpacing(8)
        tl.addWidget(QLabel("<b>Distress Records</b>  "
                            "(Add a row per distress observed; severity drives the PCI deduct)"))
        headers = ["Distress Type", "Severity", "Length (m)",
                   "Area (m^2)", "Count", "Notes", "Images"]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(True)
        tl.addWidget(self.table)
        bl.addWidget(table_card)

        # ---- Result card ---------------------------------------------
        self.res_card = Card()
        rl = QVBoxLayout(self.res_card)
        rl.setContentsMargins(20, 16, 20, 16); rl.setSpacing(6)
        rl.addWidget(QLabel("<b>Computed PCI</b>"))
        self.lbl_pci = QLabel("PCI: -")
        self.lbl_pci.setStyleSheet("font-size:18pt; font-weight:bold; color:#1d7a3a;")
        rl.addWidget(self.lbl_pci)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet("color:#6a7180; font-size:10pt;")
        rl.addWidget(self.lbl_meta)
        # Per-distress deduct summary
        self.breakdown_table = QTableWidget(0, 5)
        self.breakdown_table.setHorizontalHeaderLabels(
            ["Distress", "Severity", "Extent", "Deduct DV", "Rehab (placeholder)"]
        )
        self.breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.breakdown_table.verticalHeader().setVisible(False)
        rl.addWidget(self.breakdown_table)
        self.res_card.setVisible(False)
        bl.addWidget(self.res_card)

        # ---- Reserved-for-future banner -------------------------------
        self.lbl_future = FutureExpansionBanner(
            "Reserved for future expansion: image-based distress detection, "
            "AI-assisted classification and GIS integration are accepted in "
            "the engine API as placeholder fields but have no logic in this "
            "phase."
        )
        bl.addWidget(self.lbl_future)

        # ---- Reserved-field editor + Phase 11 image gallery -----------
        # The image-paths field is now backed by a working gallery that
        # calls the image_pipeline (Phase 11 step 2). The AI / GIS
        # fields remain stub-only — their values round-trip via JSON so
        # later phases can plug in real dialogs without restructuring
        # the input dataclass or persistence path. The PCI engine still
        # ignores all three fields.
        self.reserved_card = Card()
        rcl = QVBoxLayout(self.reserved_card)
        rcl.setContentsMargins(20, 16, 20, 16); rcl.setSpacing(8)
        rcl.addWidget(QLabel(
            "<b>Image Evidence Gallery</b>  "
            "<span style='color:#6a7180; font-size:9pt;'>"
            "(Phase 11 — files normalized to JPEG q85 / 1600 px max edge "
            "and stored under the local IMAGES_DIR. PCI engine ignores "
            "them; UI + persistence only.)"
            "</span>"
        ))

        gal_btns = QHBoxLayout()
        self.btn_add_image = styled_button("Add image...", "secondary")
        self.btn_add_image.clicked.connect(self._on_add_image)
        self.btn_remove_image = styled_button("Remove selected", "secondary")
        self.btn_remove_image.clicked.connect(self._on_remove_image)
        self.btn_open_folder = styled_button("Open folder", "secondary")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        for b in (self.btn_add_image, self.btn_remove_image, self.btn_open_folder):
            b.setEnabled(False)
            gal_btns.addWidget(b)
        gal_btns.addStretch(1)
        rcl.addLayout(gal_btns)

        self.lst_evidence = QListWidget()
        self.lst_evidence.setFixedHeight(120)
        rcl.addWidget(self.lst_evidence)

        rcl.addWidget(QLabel(
            "<b>AI / GIS Reserved Hooks  [STUB — Phase 12+]</b><br>"
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Stored with the survey; not consumed by the PCI engine."
            "</span>"
        ))

        rf_form = QFormLayout()
        self.ed_image_paths = QPlainTextEdit()
        self.ed_image_paths.setPlaceholderText(
            "Mirror of gallery — populated automatically (read-only)")
        self.ed_image_paths.setFixedHeight(60)
        self.ed_image_paths.setReadOnly(True)
        rf_form.addRow("Stored relative paths (mirror)", self.ed_image_paths)

        self.ed_ai_hint = QLineEdit()
        self.ed_ai_hint.setPlaceholderText(
            "Optional free-text hint for a future classifier")
        rf_form.addRow("AI classification hint", self.ed_ai_hint)

        self.ed_gis_geojson = QPlainTextEdit()
        self.ed_gis_geojson.setPlaceholderText(
            "Optional GeoJSON snippet (no parsing in this phase)")
        self.ed_gis_geojson.setFixedHeight(60)
        rf_form.addRow("GIS geometry (GeoJSON)", self.ed_gis_geojson)
        rcl.addLayout(rf_form)
        bl.addWidget(self.reserved_card)

        bl.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    # ---------- row management ---------------------------------------------
    def _add_row(self, distress_code: str = "cracking", severity: str = "low",
                 length_m: float = 0.0, area_m2: float = 0.0,
                 count: int = 0, notes: str = "",
                 image_paths: tuple[str, ...] = ()) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)

        cb_type = QComboBox()
        for code in _DISTRESS_CODES:
            cb_type.addItem(_DISTRESS_LABELS[code], code)
        idx = cb_type.findData(distress_code)
        if idx >= 0:
            cb_type.setCurrentIndex(idx)
        self.table.setCellWidget(r, 0, cb_type)

        cb_sev = QComboBox()
        for s in SEVERITY_LEVELS:
            cb_sev.addItem(s.title(), s)
        sidx = cb_sev.findData(severity)
        if sidx >= 0:
            cb_sev.setCurrentIndex(sidx)
        self.table.setCellWidget(r, 1, cb_sev)

        sp_len = _spin(length_m, 0, 1_000_000, 1.0, 2)
        self.table.setCellWidget(r, 2, sp_len)
        sp_area = _spin(area_m2, 0, 1_000_000, 1.0, 2)
        self.table.setCellWidget(r, 3, sp_area)
        sp_count = QSpinBox(); sp_count.setRange(0, 1_000_000); sp_count.setValue(count)
        self.table.setCellWidget(r, 4, sp_count)

        ed_notes = QLineEdit(notes)
        self.table.setCellWidget(r, 5, ed_notes)

        # Per-distress image attachment button — stores its own
        # image_paths list on the widget itself so _collect() doesn't
        # need a parallel data structure that can drift out of sync
        # with row insertion / removal.
        btn_img = QPushButton()
        btn_img._image_paths = list(image_paths)  # type: ignore[attr-defined]
        btn_img.setText(f"{len(btn_img._image_paths)} image(s)")  # type: ignore[attr-defined]
        btn_img.clicked.connect(
            lambda _checked=False, b=btn_img: self._on_open_distress_images(b)
        )
        self.table.setCellWidget(r, 6, btn_img)

    def _remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    # ---------- collect / compute / save / export --------------------------
    def _collect(self) -> ConditionSurveyInput:
        records: list[DistressRecord] = []
        for r in range(self.table.rowCount()):
            cb_t = self.table.cellWidget(r, 0)
            cb_s = self.table.cellWidget(r, 1)
            sp_l = self.table.cellWidget(r, 2)
            sp_a = self.table.cellWidget(r, 3)
            sp_c = self.table.cellWidget(r, 4)
            ed_n = self.table.cellWidget(r, 5)
            btn_img = self.table.cellWidget(r, 6)
            if cb_t is None or cb_s is None:
                continue
            row_imgs = tuple(getattr(btn_img, "_image_paths", ()) or ())
            records.append(DistressRecord(
                distress_type=cb_t.currentData() or "cracking",
                severity=cb_s.currentData() or "low",
                length_m=float(sp_l.value()) if sp_l else 0.0,
                area_m2=float(sp_a.value()) if sp_a else 0.0,
                count=int(sp_c.value()) if sp_c else 0,
                notes=ed_n.text() if ed_n else "",
                image_paths=row_imgs,
            ))
        # Image evidence: prefer the gallery model when present. Fall
        # back to parsing the (read-only) mirror textarea so callers
        # that inject paths programmatically (e.g. legacy/smoke flows
        # that set ed_image_paths directly) still round-trip.
        if self._evidence:
            image_paths = tuple(self._evidence)
        else:
            image_paths = tuple(
                line.strip()
                for line in self.ed_image_paths.toPlainText().splitlines()
                if line.strip()
            )
        return ConditionSurveyInput(
            work_name=self.work_name.text(),
            surveyed_by=self.surveyed_by.text(),
            survey_date=self.survey_date.text(),
            chainage_from_km=float(self.ch_from.value()),
            chainage_to_km=float(self.ch_to.value()),
            lane_id=self.lane_id.text(),
            records=tuple(records),
            image_paths=image_paths,
            ai_classification_hint=self.ed_ai_hint.text(),
            gis_geometry_geojson=self.ed_gis_geojson.toPlainText(),
        )

    def _on_compute(self) -> None:
        try:
            r = compute_condition_survey(self._collect())
        except Exception as e:
            QMessageBox.critical(self, "Computation error", str(e))
            return
        self._last = r
        self.res_card.setVisible(True)
        self.lbl_pci.setText(
            f"PCI = {r.pci_score:.2f}   ({r.condition_category})"
        )
        self.lbl_meta.setText(
            f"Total Deduct = {r.total_deduct:.2f}  -  "
            f"Records = {len(r.breakdown)}  -  "
            f"Calibration: PLACEHOLDER"
        )
        # populate breakdown table
        self.breakdown_table.setRowCount(len(r.breakdown))
        for i, b in enumerate(r.breakdown):
            t = DISTRESS_TYPES.get(b.distress_type)
            label = t.label if t else b.distress_type
            extent_txt = (f"{b.extent_value:g} {b.extent_unit.replace('_', ' ')}"
                          if b.extent_unit else "-")
            ref = b.recommendation.reference
            rehab_txt = f"{b.recommendation.treatment} ({ref.code_id})"
            cells = [label, b.severity.title(), extent_txt,
                     f"{b.deduct_value:.2f}", rehab_txt]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                self.breakdown_table.setItem(i, c, item)
        self.btn_save.setEnabled(self._project_id is not None)

    def _on_save(self) -> None:
        if self._project_id is None or self._last is None:
            return
        try:
            self.db.save_condition_survey(
                project_id=self._project_id, result=self._last)
            self.db.set_module_status(self._project_id, "condition", "complete")
            self.btn_export.setEnabled(True)
            QMessageBox.information(self, "Saved",
                "Pavement condition survey saved to this project.")
            self.saved.emit(self._project_id)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export(self) -> None:
        if self._project_id is None:
            return
        self.export_requested.emit(self._project_id)

    # ---------- image-evidence gallery (Phase 11) --------------------------
    def _refresh_evidence_mirror(self) -> None:
        """Sync the read-only ed_image_paths textarea from self._evidence."""
        self.ed_image_paths.setPlainText("\n".join(self._evidence))

    def _evidence_row_label(self, rel_path: str) -> str:
        abs_path = IMAGES_DIR / Path(rel_path)
        if not abs_path.is_file():
            return f"{rel_path}  (missing)"
        try:
            size_kb = abs_path.stat().st_size / 1024.0
            return f"{abs_path.name}  -  {size_kb:.1f} KB  -  {rel_path}"
        except OSError:
            return rel_path

    def _rebuild_evidence_list_widget(self) -> None:
        self.lst_evidence.clear()
        for rel in self._evidence:
            item = QListWidgetItem(self._evidence_row_label(rel))
            item.setData(Qt.UserRole, rel)
            self.lst_evidence.addItem(item)

    def _set_gallery_enabled(self, enabled: bool) -> None:
        for b in (self.btn_add_image, self.btn_remove_image,
                  self.btn_open_folder):
            b.setEnabled(enabled)

    def _on_add_image(self) -> None:
        if self._project_id is None:
            QMessageBox.warning(self, "No project",
                "Create or load a project before attaching images.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach pavement image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not paths:
            return
        added: list[str] = []
        for p in paths:
            try:
                ev = attach_image(self._project_id, DRAFT_SURVEY_ID, p)
            except Exception as e:
                QMessageBox.warning(self, "Image rejected",
                    f"Could not attach {p}:\n{e}")
                continue
            if ev.relative_path in self._evidence:
                continue  # dedup — content-addressed pipeline already did
            self._evidence.append(ev.relative_path)
            added.append(ev.relative_path)
        if added:
            self._rebuild_evidence_list_widget()
            self._refresh_evidence_mirror()

    def _on_remove_image(self) -> None:
        if self._project_id is None:
            return
        item = self.lst_evidence.currentItem()
        if item is None:
            return
        rel = item.data(Qt.UserRole)
        if not rel:
            return
        try:
            delete_evidence(self._project_id, DRAFT_SURVEY_ID, rel)
        except Exception:
            pass  # best-effort; we still drop the panel reference
        if rel in self._evidence:
            self._evidence.remove(rel)
        self._rebuild_evidence_list_widget()
        self._refresh_evidence_mirror()

    def _on_open_folder(self) -> None:
        if self._project_id is None:
            return
        folder = IMAGES_DIR / "condition" / str(self._project_id)
        folder.mkdir(parents=True, exist_ok=True)
        _open_in_file_browser(folder)

    def _on_open_distress_images(self, btn: QPushButton) -> None:
        """Open the per-distress image dialog for the row owning ``btn``."""
        if self._project_id is None:
            QMessageBox.warning(self, "No project",
                "Create or load a project before attaching images.")
            return
        # Resolve the distress label for the dialog title from the row's
        # type combobox (the panel doesn't track row->label outside the
        # table widget).
        row = -1
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 6) is btn:
                row = r
                break
        if row < 0:
            return
        cb_t = self.table.cellWidget(row, 0)
        code = cb_t.currentData() if cb_t is not None else "cracking"
        label = _DISTRESS_LABELS.get(code, code)
        dlg = DistressImagesDialog(
            project_id=self._project_id,
            distress_label=label,
            initial_paths=tuple(getattr(btn, "_image_paths", ()) or ()),
            parent=self,
        )
        dlg.exec()
        btn._image_paths = list(dlg.image_paths())  # type: ignore[attr-defined]
        btn.setText(f"{len(btn._image_paths)} image(s)")  # type: ignore[attr-defined]

    # ---------- project binding --------------------------------------------
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        # Clear table + reserved-field widgets on project switch
        self.table.setRowCount(0)
        self.breakdown_table.setRowCount(0)
        self._evidence = []
        self.lst_evidence.clear()
        self.ed_image_paths.setPlainText("")
        self.ed_ai_hint.setText("")
        self.ed_gis_geojson.setPlainText("")
        self._set_gallery_enabled(pid is not None)
        if pid is None:
            self.proj_banner.setText("[WARN] No project loaded.")
            self.btn_export.setEnabled(False)
            return
        self.proj_banner.setText(f"<b>Project #{pid}:</b> {name or '(unnamed)'}")
        row = self.db.latest_condition_survey(pid)
        self.btn_export.setEnabled(row is not None)
        if row and row.inputs_json:
            try:
                d = json.loads(row.inputs_json)
                self.work_name.setText(d.get("work_name", "") or "")
                self.surveyed_by.setText(d.get("surveyed_by", "") or "")
                self.survey_date.setText(d.get("survey_date", "") or "")
                self.lane_id.setText(d.get("lane_id", "") or "")
                self.ch_from.setValue(float(d.get("chainage_from_km") or 0))
                self.ch_to.setValue(float(d.get("chainage_to_km") or 0))
                for rec in (d.get("records") or ()):
                    self._add_row(
                        distress_code=rec.get("distress_type", "cracking"),
                        severity=rec.get("severity", "low"),
                        length_m=float(rec.get("length_m") or 0),
                        area_m2=float(rec.get("area_m2") or 0),
                        count=int(rec.get("count") or 0),
                        notes=rec.get("notes", "") or "",
                        image_paths=tuple(rec.get("image_paths") or ()),
                    )
                # Image evidence reload — restore the saved relative
                # paths verbatim (including any that no longer resolve
                # on disk; the gallery row label flags them as missing).
                self._evidence = list(d.get("image_paths") or ())
                self._rebuild_evidence_list_widget()
                self._refresh_evidence_mirror()
                # AI / GIS hooks remain stub-only.
                self.ed_ai_hint.setText(d.get("ai_classification_hint", "") or "")
                self.ed_gis_geojson.setPlainText(d.get("gis_geometry_geojson", "") or "")
            except Exception:
                pass

    def last_result(self) -> ConditionSurveyResult | None:
        return self._last
