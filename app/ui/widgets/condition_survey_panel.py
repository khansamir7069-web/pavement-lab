"""Pavement Condition Survey panel — Phase 10.

Independent panel mirroring TrafficPanel: metadata header + distress
table (add/remove rows) + Compute + Save + Export Word.

Image / AI / GIS fields are accepted in ConditionSurveyInput but exposed
on this panel only as a read-only reserved-for-future banner.
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
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    DISTRESS_TYPES,
    SEVERITY_LEVELS,
    ConditionSurveyInput,
    ConditionSurveyResult,
    DistressRecord,
    compute_condition_survey,
)
from .common import (
    Card,
    FutureExpansionBanner,
    InfoBanner,
    PageHeader,
    PlaceholderBanner,
    styled_button,
)


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


class ConditionSurveyPanel(QWidget):
    """Independent pavement condition survey page."""

    saved = Signal(int)
    export_requested = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._project_id: int | None = None
        self._last: ConditionSurveyResult | None = None
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
                   "Area (m^2)", "Count", "Notes"]
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

        # ---- Reserved-field editor (Phase 11/12 hooks — STUB) ---------
        # Three widgets bound to ConditionSurveyInput.image_paths /
        # .ai_classification_hint / .gis_geometry_geojson. The values
        # round-trip through save/load JSON so Phase 11/12 can replace
        # the stub widgets with real dialogs without restructuring the
        # input dataclass or persistence path. The engine still ignores
        # all three fields in this phase.
        self.reserved_card = Card()
        rcl = QVBoxLayout(self.reserved_card)
        rcl.setContentsMargins(20, 16, 20, 16); rcl.setSpacing(8)
        rcl.addWidget(QLabel(
            "<b>Reserved Field Hooks  [STUB — Phase 11/12]</b><br>"
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Values entered here are saved with the survey but are NOT "
            "consumed by the PCI engine in this phase. They exist so the "
            "image / AI / GIS dialogs of later phases can plug in without "
            "changing the input dataclass or DB schema."
            "</span>"
        ))

        rf_form = QFormLayout()
        self.ed_image_paths = QPlainTextEdit()
        self.ed_image_paths.setPlaceholderText(
            "One image path per line (no logic in this phase)")
        self.ed_image_paths.setFixedHeight(60)
        rf_form.addRow("Image paths (one per line)", self.ed_image_paths)

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
                 count: int = 0, notes: str = "") -> None:
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
            if cb_t is None or cb_s is None:
                continue
            records.append(DistressRecord(
                distress_type=cb_t.currentData() or "cracking",
                severity=cb_s.currentData() or "low",
                length_m=float(sp_l.value()) if sp_l else 0.0,
                area_m2=float(sp_a.value()) if sp_a else 0.0,
                count=int(sp_c.value()) if sp_c else 0,
                notes=ed_n.text() if ed_n else "",
            ))
        # Reserved-field editors — values are stored but the engine
        # ignores them in this phase. See ConditionSurveyInput docstring.
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

    # ---------- project binding --------------------------------------------
    def set_project(self, pid: int | None, name: str = "") -> None:
        self._project_id = pid
        self._last = None
        self.btn_save.setEnabled(False)
        self.res_card.setVisible(False)
        # Clear table + reserved-field widgets on project switch
        self.table.setRowCount(0)
        self.breakdown_table.setRowCount(0)
        self.ed_image_paths.setPlainText("")
        self.ed_ai_hint.setText("")
        self.ed_gis_geojson.setPlainText("")
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
                    )
                # Reserved-field reload (Phase 11/12 hooks — stored only)
                self.ed_image_paths.setPlainText(
                    "\n".join(d.get("image_paths") or ())
                )
                self.ed_ai_hint.setText(d.get("ai_classification_hint", "") or "")
                self.ed_gis_geojson.setPlainText(d.get("gis_geometry_geojson", "") or "")
            except Exception:
                pass

    def last_result(self) -> ConditionSurveyResult | None:
        return self._last
