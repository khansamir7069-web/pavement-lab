"""Tabbed inputs panel: Gradation | Sp.Gr. | Gmb | Gmm | Stability/Flow.

All inputs live in one widget so the engine receives a single coherent
payload when the user hits "Compute". Lab-data cells are intentionally
blank on startup so operators enter measured values explicitly.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import (
    BitumenSGInput,
    CoarseAggSGInput,
    FineAggSGInput,
    GmbGroup,
    GmbInput,
    GmbSpecimen,
    GmmInput,
    GmmSampleRaw,
    GradationInput,
    MaterialCalcInput,
    MIX_SPECS,
    MIX_TYPES,
    StabilityFlowInput,
    StabilitySpecimen,
)
from .common import PageHeader, PlaceholderBanner, styled_button


# Fallback gradation envelope used only before a project mix type is selected.
# Lab-data cells remain blank until the operator fills them.
SIEVES = (37.5, 26.5, 19, 13.2, 4.75, 2.36, 0.3, 0.075)
AVAILABLE_AGGS = ("25mm", "20mm", "10mm", "6mm", "SD", "Cement")
AGGS = ("25mm", "20mm", "6mm", "SD", "Cement")
MATERIAL_DISPLAY_NAMES = {
    "25mm": "25 mm",
    "20mm": "20 mm",
    "10mm": "10 mm",
    "6mm": "6 mm",
    "SD": "Stone Dust",
    "Cement": "Cement",
}
BLANK_MARSHALL_ROWS = 15
BLANK_GMM_ROWS = 2


# ---------- helper utilities ----------------------------------------------

def _set_num(table: QTableWidget, r: int, c: int, v: float, decimals: int = 2) -> None:
    item = QTableWidgetItem(f"{v:.{decimals}f}" if v is not None else "")
    item.setTextAlignment(Qt.AlignCenter)
    table.setItem(r, c, item)


def _get_num(table: QTableWidget, r: int, c: int, default: float = 0.0) -> float:
    item = table.item(r, c)
    if not item or not item.text().strip():
        return default
    try:
        return float(item.text())
    except ValueError:
        return default


def _cell_text(table: QTableWidget, r: int, c: int) -> str:
    item = table.item(r, c)
    return item.text().strip() if item and item.text() else ""


def _set_blank(table: QTableWidget, r: int, c: int) -> None:
    item = QTableWidgetItem("")
    item.setTextAlignment(Qt.AlignCenter)
    table.setItem(r, c, item)


def _require_table_num(table: QTableWidget, r: int, c: int, label: str) -> float:
    text = _cell_text(table, r, c)
    if not text:
        raise ValueError(f"Missing {label}. Fill the field before computing.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {label}: {text!r}.") from exc


def _optional_table_num(table: QTableWidget, r: int, c: int, label: str) -> float | None:
    text = _cell_text(table, r, c)
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {label}: {text!r}.") from exc


def _line_num(widget: QLineEdit, label: str) -> float:
    text = widget.text().strip()
    if not text:
        raise ValueError(f"Missing {label}. Fill the field before computing.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {label}: {text!r}.") from exc


def _row_has_any(table: QTableWidget, r: int, cols: tuple[int, ...]) -> bool:
    return any(_cell_text(table, r, c) for c in cols)


def _active_material_text(active_materials: tuple[str, ...] | list[str]) -> str:
    labels = [MATERIAL_DISPLAY_NAMES.get(name, name) for name in active_materials]
    return "Active materials: " + (", ".join(labels) if labels else "none selected")


def _set_text(table: QTableWidget, r: int, c: int, text: str) -> None:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    item.setTextAlignment(Qt.AlignCenter)
    item.setBackground(QColor(240, 243, 248))
    table.setItem(r, c, item)


def _checkbox_item(checked: bool = True) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    item.setTextAlignment(Qt.AlignCenter)
    return item


# ---------- fallback specification envelope -------------------------------

FALLBACK_SPEC_LOW = (100, 90, 71, 56, 38, 28, 7, 2)
FALLBACK_SPEC_UP  = (100, 100, 95, 80, 54, 42, 21, 8)


# ---------- gradation tab --------------------------------------------------

class GradationTab(QWidget):
    active_materials_changed = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sieves: tuple[float, ...] = SIEVES
        self._available_aggs: tuple[str, ...] = AVAILABLE_AGGS
        self._aggs: tuple[str, ...] = AGGS
        self._mix_type_key: str = ""
        self._mix_code_label = QLabel("")
        self._mix_code_label.setStyleSheet(
            "color:#1f3a68; font-size:10pt; font-weight:bold;"
        )
        self._warning_banner = PlaceholderBanner()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._mix_code_label)
        layout.addWidget(self._warning_banner)

        self.active_checks: dict[str, QCheckBox] = {}
        self.material_group = QGroupBox("Active material selection")
        self.material_group.setObjectName("ActiveMaterialSelection")
        self.material_group.setStyleSheet(
            """
            QGroupBox#ActiveMaterialSelection {
                background:#ffffff;
                border:1px solid #c9d6ec;
                border-radius:6px;
                margin-top:14px;
                padding:10px 10px 8px 10px;
                color:#1f3a68;
                font-weight:bold;
            }
            QGroupBox#ActiveMaterialSelection::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left:10px;
                padding:0 6px;
                background:#ffffff;
            }
            QGroupBox#ActiveMaterialSelection QCheckBox {
                spacing:8px;
                padding:6px 10px;
                border:1px solid #c5ccda;
                border-radius:4px;
                background:#f9fafc;
                color:#1f3a68;
                font-weight:normal;
            }
            QGroupBox#ActiveMaterialSelection QCheckBox:checked {
                background:#eaf4ee;
                border-color:#5d9b6e;
                color:#185d33;
                font-weight:bold;
            }
            QGroupBox#ActiveMaterialSelection QCheckBox::indicator {
                width:16px;
                height:16px;
            }
            """
        )
        material_layout = QVBoxLayout(self.material_group)
        material_layout.setContentsMargins(10, 14, 10, 10)
        material_layout.setSpacing(8)
        self._active_summary = QLabel("")
        self._active_summary.setObjectName("ActiveMaterialSummary")
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt; font-weight:normal;")
        material_layout.addWidget(self._active_summary)
        self._material_grid = QGridLayout()
        self._material_grid.setHorizontalSpacing(8)
        self._material_grid.setVerticalSpacing(8)
        for idx, name in enumerate(self._available_aggs):
            cb = QCheckBox(MATERIAL_DISPLAY_NAMES.get(name, name))
            cb.setToolTip(
                "Enable this component in gradation, blend ratio, calculation, and report output."
            )
            cb.setChecked(name in self._aggs)
            cb.stateChanged.connect(self._on_active_materials_changed)
            self.active_checks[name] = cb
            self._material_grid.addWidget(cb, idx // 3, idx % 3)
        material_layout.addLayout(self._material_grid)
        layout.addWidget(self.material_group)

        # Blend ratios row (small)
        self._blend_form = QFormLayout()
        self.blend_spins: dict[str, QLineEdit] = {}
        self.blend_labels: dict[str, QLabel] = {}
        self._blend_row_widget = QWidget()
        self._blend_row = QHBoxLayout(self._blend_row_widget)
        self._blend_row.setContentsMargins(0, 0, 0, 0)
        for name in self._available_aggs:
            sp = QLineEdit()
            sp.setValidator(QDoubleValidator(0.0, 1.0, 3, self))
            lbl = QLabel(MATERIAL_DISPLAY_NAMES.get(name, name))
            self.blend_spins[name] = sp
            self.blend_labels[name] = lbl
            self._blend_row.addWidget(lbl)
            self._blend_row.addWidget(sp)
        self._blend_form.addRow("Blend Ratios (sum to 1.000):", self._blend_row_widget)
        layout.addLayout(self._blend_form)

        # Gradation table
        headers = ["IS Sieve (mm)"] + [
            MATERIAL_DISPLAY_NAMES.get(name, name) for name in self._available_aggs
        ] + ["MoRTH Lower", "MoRTH Upper"]
        self.table = QTableWidget(len(self._sieves), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r, sieve in enumerate(self._sieves):
            _set_text(self.table, r, 0, f"{sieve:g}")
            for ci, name in enumerate(self._available_aggs, start=1):
                _set_blank(self.table, r, ci)
            _set_num(self.table, r, len(self._available_aggs) + 1, FALLBACK_SPEC_LOW[r], decimals=0)
            _set_num(self.table, r, len(self._available_aggs) + 2, FALLBACK_SPEC_UP[r], decimals=0)
        self._sync_active_materials()
        layout.addWidget(self.table)

    def active_materials(self) -> tuple[str, ...]:
        return tuple(
            name for name in self._available_aggs
            if self.active_checks[name].isChecked()
        )

    def set_active_materials(self, names) -> None:
        wanted = {str(n).strip() for n in names if str(n).strip()}
        for name, cb in self.active_checks.items():
            cb.blockSignals(True)
            cb.setChecked(name in wanted)
            cb.blockSignals(False)
        self._sync_active_materials()

    def _on_active_materials_changed(self, *_args) -> None:
        self._sync_active_materials()

    def _sync_active_materials(self) -> None:
        self._aggs = self.active_materials()
        active = set(self._aggs)
        active_labels = [MATERIAL_DISPLAY_NAMES.get(name, name) for name in self._aggs]
        self._active_summary.setText(
            "Active: " + ", ".join(active_labels)
            if active_labels else
            "Active: none selected"
        )
        for name in self._available_aggs:
            visible = name in active
            self.blend_labels[name].setVisible(visible)
            self.blend_spins[name].setVisible(visible)
            self.table.setColumnHidden(self._available_aggs.index(name) + 1, not visible)
        self.active_materials_changed.emit(self._aggs)

    def set_mix_type(self, mix_type_key: str) -> None:
        """Rebuild the gradation table from MIX_TYPES[mix_type_key].

        Replaces sieve set, lower/upper envelope from the spec database
        (Phase 6 source-tagged). Per-aggregate passing% cells are cleared
        because the source envelope changes by mix type. The active material selector
        keeps the user's chosen aggregate fractions when the envelope changes.
        Surfaces the placeholder warning banner when status is unverified.
        """
        record = MIX_TYPES.get(mix_type_key) if mix_type_key else None
        if not record or not record.sieve_sizes_mm:
            # Fallback: leave the generic startup envelope in place
            self._mix_type_key = ""
            self._mix_code_label.setText("")
            self._warning_banner.setVisible(False)
            return

        self._mix_type_key = record.mix_code
        self._sieves = tuple(record.sieve_sizes_mm)
        lower = tuple(record.gradation_lower) if record.gradation_lower else tuple(
            None for _ in self._sieves
        )
        upper = tuple(record.gradation_upper) if record.gradation_upper else tuple(
            None for _ in self._sieves
        )

        # Header label with mix code + applicable code (Phase 6 source tag)
        # + compaction blows from MIX_SPECS (F3 — Phase-9 audit close-out).
        src = record.applicable_code or "—"
        spec = MIX_SPECS.get(record.mix_code)
        blows_txt = (
            f"    •    Compaction: {spec.compaction_blows_each_face} blows/face"
            if spec else ""
        )
        self._mix_code_label.setText(
            f"Mix: {record.mix_code} — {record.full_name}"
            f"    •    Spec: {src}{blows_txt}"
        )

        # Placeholder warning banner (F2)
        if (record.status or "").strip() == "placeholder_editable":
            self._warning_banner.set_message(
                f"⚠ Spec limits and gradation envelope for {record.mix_code} "
                f"are not IRC-verified. Results are indicative — confirm against "
                f"the relevant IRC clause before adoption. (Source: "
                f"{record.applicable_code or 'unverified'})"
            )
        else:
            self._warning_banner.set_message("", visible=False)

        # Rebuild table with new sieve count
        headers = ["IS Sieve (mm)"] + [
            MATERIAL_DISPLAY_NAMES.get(name, name) for name in self._available_aggs
        ] + ["MoRTH Lower", "MoRTH Upper"]
        self.table.setRowCount(len(self._sieves))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for r, sieve in enumerate(self._sieves):
            _set_text(self.table, r, 0, f"{sieve:g}")
            for ci, _name in enumerate(self._available_aggs, start=1):
                # Clear per-aggregate lab-data cells when the envelope changes
                self.table.setItem(r, ci, QTableWidgetItem(""))
            lo = lower[r] if r < len(lower) else None
            hi = upper[r] if r < len(upper) else None
            if lo is not None:
                _set_num(self.table, r, len(self._available_aggs) + 1, float(lo), decimals=0)
            else:
                self.table.setItem(r, len(self._available_aggs) + 1, QTableWidgetItem(""))
            if hi is not None:
                _set_num(self.table, r, len(self._available_aggs) + 2, float(hi), decimals=0)
            else:
                self.table.setItem(r, len(self._available_aggs) + 2, QTableWidgetItem(""))
        self._sync_active_materials()

    def collect(self) -> GradationInput:
        if len(self._aggs) < 2:
            raise ValueError("Select at least two active materials before computing gradation.")
        if len(set(self._aggs)) != len(self._aggs) or any(not n.strip() for n in self._aggs):
            raise ValueError("Active material names must be non-blank and unique.")
        blend = {
            n: _line_num(
                self.blend_spins[n],
                f"blend ratio for {MATERIAL_DISPLAY_NAMES.get(n, n)}",
            )
            for n in self._aggs
        }
        if abs(sum(blend.values()) - 1.0) > 0.001:
            raise ValueError("Blend ratios for active materials must sum to 1.000.")
        pass_pct = {}
        for name in self._aggs:
            ci = self._available_aggs.index(name) + 1
            missing = [
                r for r in range(len(self._sieves))
                if not (self.table.item(r, ci) and self.table.item(r, ci).text().strip())
            ]
            if missing:
                raise ValueError(
                    f"Missing gradation data for active material {name}. "
                    "Fill all sieve passing values or deactivate this material."
                )
            pass_pct[name] = tuple(_get_num(self.table, r, ci) for r in range(len(self._sieves)))
        spec_low = tuple(_get_num(self.table, r, len(self._available_aggs) + 1) for r in range(len(self._sieves)))
        spec_up = tuple(_get_num(self.table, r, len(self._available_aggs) + 2) for r in range(len(self._sieves)))
        return GradationInput(
            sieve_sizes_mm=tuple(self._sieves),
            pass_pct=pass_pct,
            blend_ratios=blend,
            spec_lower=spec_low,
            spec_upper=spec_up,
        )


# ---------- specific-gravity tab ------------------------------------------

class SpGrTab(QWidget):
    """Specific-gravity mini-tables for active aggregate fractions + bitumen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._active_summary = QLabel(_active_material_text(AGGS))
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt;")
        layout.addWidget(self._active_summary)
        self._material_labels: dict[str, QLabel] = {}

        # 25mm coarse
        self._material_labels["25mm"] = QLabel("<b>Coarse Aggregate 25 mm  (Wire Basket / IS 2386-III)</b>")
        layout.addWidget(self._material_labels["25mm"])
        self.coarse_25 = QTableWidget(4, 4)
        self.coarse_25.setVerticalHeaderLabels(["A — sample+container in water",
                                                "B — container in water",
                                                "C — SSD in air",
                                                "D — oven-dry in air"])
        self.coarse_25.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.coarse_25.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.coarse_25)

        # 20mm coarse
        self._material_labels["20mm"] = QLabel("<b>Coarse Aggregate 20 mm</b>")
        layout.addWidget(self._material_labels["20mm"])
        self.coarse_20 = QTableWidget(4, 4)
        self.coarse_20.setVerticalHeaderLabels(["A", "B", "C", "D"])
        self.coarse_20.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.coarse_20.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.coarse_20)

        # 10mm coarse - optional V1.1 user-selectable component.
        self._material_labels["10mm"] = QLabel("<b>Coarse Aggregate 10 mm</b>")
        layout.addWidget(self._material_labels["10mm"])
        self.coarse_10 = QTableWidget(4, 4)
        self.coarse_10.setVerticalHeaderLabels(["A", "B", "C", "D"])
        self.coarse_10.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.coarse_10.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.coarse_10)

        # 6mm fine (pycnometer)
        self._material_labels["6mm"] = QLabel("<b>Fine Aggregate 6 mm  (Pycnometer)</b>")
        layout.addWidget(self._material_labels["6mm"])
        self.fine_6 = QTableWidget(4, 4)
        self.fine_6.setVerticalHeaderLabels(["W1 — empty",
                                             "W2 — + dry sample",
                                             "W3 — + dry sample + water",
                                             "W4 — + water"])
        self.fine_6.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.fine_6.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.fine_6)

        # Stone dust
        self._material_labels["SD"] = QLabel("<b>Stone Dust  (Pycnometer)</b>")
        layout.addWidget(self._material_labels["SD"])
        self.fine_sd = QTableWidget(4, 4)
        self.fine_sd.setVerticalHeaderLabels(["W1", "W2", "W3", "W4"])
        self.fine_sd.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.fine_sd.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.fine_sd)
        self.set_active_materials(AGGS)

        # Bitumen
        layout.addWidget(QLabel("<b>Bitumen VG-30  (Sp. Gr. Bottle)</b>"))
        self.bitumen = QTableWidget(4, 4)
        self.bitumen.setVerticalHeaderLabels(["A — empty bottle",
                                              "B — bottle + water",
                                              "C — bottle + sample",
                                              "D — bottle + sample + water"])
        self.bitumen.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.bitumen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.bitumen)

    def _collect_complete_reps(
        self,
        t: QTableWidget,
        label: str,
        row_labels: tuple[str, str, str, str],
    ) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        by_row: list[list[float]] = [[], [], [], []]
        for c in range(t.columnCount()):
            texts = [_cell_text(t, r, c) for r in range(4)]
            if not any(texts):
                continue
            if not all(texts):
                missing = [row_labels[i] for i, text in enumerate(texts) if not text]
                raise ValueError(
                    f"Missing {label} data in Rep {c + 1}: "
                    + ", ".join(missing)
                    + ". Fill the complete repetition or leave it blank."
                )
            for r, row_label in enumerate(row_labels):
                by_row[r].append(_require_table_num(t, r, c, f"{label} Rep {c + 1} {row_label}"))
        if not by_row[0]:
            raise ValueError(f"Missing specific-gravity data for {label}. Fill at least one complete repetition.")
        return tuple(tuple(row) for row in by_row)  # type: ignore[return-value]

    def _collect_coarse(self, t: QTableWidget) -> CoarseAggSGInput:
        A, B, C, D = self._collect_complete_reps(t, "coarse aggregate", ("A", "B", "C", "D"))
        return CoarseAggSGInput(A, B, C, D)

    def _collect_fine(self, t: QTableWidget) -> FineAggSGInput:
        W1, W2, W3, W4 = self._collect_complete_reps(t, "fine aggregate", ("W1", "W2", "W3", "W4"))
        return FineAggSGInput(W1, W2, W3, W4)

    def set_active_materials(self, active_materials: tuple[str, ...] | list[str]) -> None:
        active = set(active_materials)
        self._active_summary.setText(_active_material_text(tuple(active_materials)))
        tables = {
            "25mm": self.coarse_25,
            "20mm": self.coarse_20,
            "10mm": self.coarse_10,
            "6mm": self.fine_6,
            "SD": self.fine_sd,
        }
        for name, table in tables.items():
            visible = name in active
            self._material_labels[name].setVisible(visible)
            table.setVisible(visible)

    def collect(self, active_materials: tuple[str, ...] | None = None) -> tuple[dict, dict, BitumenSGInput]:
        active = set(active_materials or AGGS)
        coarse_tables = {
            "25mm": self.coarse_25,
            "20mm": self.coarse_20,
            "10mm": self.coarse_10,
        }
        fine_tables = {
            "6mm": self.fine_6,
            "SD": self.fine_sd,
        }
        coarse = {
            name: self._collect_coarse(table)
            for name, table in coarse_tables.items()
            if name in active
        }
        fine = {
            name: self._collect_fine(table)
            for name, table in fine_tables.items()
            if name in active
        }
        A, B, C, D = self._collect_complete_reps(self.bitumen, "bitumen", ("A", "B", "C", "D"))
        bit = BitumenSGInput(A, B, C, D)
        return coarse, fine, bit


# ---------- Gmb tab --------------------------------------------------------

class GmbTab(QWidget):
    """5 Pb groups × 3 specimens, columns: A | C (water) | B (SSD)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel(
            "<b>Gmb — Bulk SG of compacted specimens</b>  "
            "(5 bitumen contents × 3 specimens)"
        ))
        headers = ["Pb %", "Sample", "A — dry in air", "C — in water",
                   "B — SSD in air"]
        self._active_summary = QLabel(_active_material_text(AGGS))
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt;")
        layout.addWidget(self._active_summary)
        self.table = QTableWidget(BLANK_MARSHALL_ROWS, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                _set_blank(self.table, r, c)
        layout.addWidget(self.table)

    def set_active_materials(self, active_materials: tuple[str, ...] | list[str]) -> None:
        self._active_summary.setText(_active_material_text(tuple(active_materials)))

    def collect(self) -> GmbInput:
        groups: dict[float, list[GmbSpecimen]] = {}
        order: list[float] = []
        for r in range(self.table.rowCount()):
            data_cols = (0, 2, 3, 4)
            if not _row_has_any(self.table, r, data_cols):
                continue
            pb = _require_table_num(self.table, r, 0, f"Gmb row {r + 1} Pb %")
            A = _require_table_num(self.table, r, 2, f"Gmb row {r + 1} dry in air")
            C = _require_table_num(self.table, r, 3, f"Gmb row {r + 1} in water")
            B = _require_table_num(self.table, r, 4, f"Gmb row {r + 1} SSD in air")
            sp = GmbSpecimen(a_dry_in_air=A, c_in_water=C, b_ssd_in_air=B)
            if pb not in groups:
                groups[pb] = []
                order.append(pb)
            groups[pb].append(sp)
        if not order:
            raise ValueError("Missing Gmb data. Fill at least one complete Gmb specimen row before computing.")
        return GmbInput(groups=tuple(
            GmbGroup(bitumen_pct=pb, specimens=tuple(groups[pb])) for pb in order
        ))


# ---------- Gmm tab --------------------------------------------------------

class GmmTab(QWidget):
    """Reference Pb Rice test (2 samples) + design Pb list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(QLabel("<b>Reference Pb for Rice test</b>"))
        self._active_summary = QLabel(_active_material_text(AGGS))
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt;")
        layout.addWidget(self._active_summary)
        row = QHBoxLayout()
        self.pb_ref = QLineEdit()
        self.pb_ref.setValidator(QDoubleValidator(0.0, 20.0, 2, self))
        row.addWidget(QLabel("Pb_ref (%)"))
        row.addWidget(self.pb_ref)
        row.addStretch(1)
        layout.addLayout(row)

        headers = ["Sample", "A — empty flask", "B — flask + dry sample",
                   "D — flask + water", "E — flask + sample + water"]
        self.table = QTableWidget(BLANK_GMM_ROWS, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                _set_blank(self.table, r, c)
        layout.addWidget(self.table)

    def set_active_materials(self, active_materials: tuple[str, ...] | list[str]) -> None:
        self._active_summary.setText(_active_material_text(tuple(active_materials)))

    def collect(self, bitumen_sg: float, design_pb_pct: tuple[float, ...]) -> GmmInput:
        if not design_pb_pct:
            raise ValueError("Missing design bitumen contents. Fill Gmb rows before computing Gmm.")
        samples: list[GmmSampleRaw] = []
        for r in range(self.table.rowCount()):
            data_cols = (1, 2, 3, 4)
            if not _row_has_any(self.table, r, data_cols):
                continue
            samples.append(
                GmmSampleRaw(
                    a_empty_flask=_require_table_num(self.table, r, 1, f"Gmm row {r + 1} empty flask"),
                    b_flask_plus_dry_sample=_require_table_num(self.table, r, 2, f"Gmm row {r + 1} flask + dry sample"),
                    d_flask_filled_water=_require_table_num(self.table, r, 3, f"Gmm row {r + 1} flask + water"),
                    e_flask_sample_water=_require_table_num(self.table, r, 4, f"Gmm row {r + 1} flask + sample + water"),
                )
            )
        if not samples:
            raise ValueError("Missing Gmm data. Fill at least one complete Rice-test sample before computing.")
        return GmmInput(
            reference_pb_pct=_line_num(self.pb_ref, "Gmm reference Pb"),
            samples_at_reference=tuple(samples),
            design_pb_pct=design_pb_pct,
            bitumen_sg=bitumen_sg,
        )


# ---------- Stability/Flow tab --------------------------------------------

class StabilityFlowTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel(
            "<b>Marshall Stability and Flow</b>  "
            "(per-specimen include columns let you exclude failed-height samples)"
        ))
        self._active_summary = QLabel(_active_material_text(AGGS))
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt;")
        layout.addWidget(self._active_summary)
        headers = [
            "Pb %", "Sample", "H1", "H2", "H3", "Dia mm", "Corr. Factor",
            "Measured Stab. (kN)", "Flow (mm)", "N override (opt)",
            "Inc Stab", "Inc Flow",
        ]
        self.table = QTableWidget(BLANK_MARSHALL_ROWS, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r in range(self.table.rowCount()):
            for c in range(10):
                _set_blank(self.table, r, c)
            self.table.setItem(r, 10, _checkbox_item(True))
            self.table.setItem(r, 11, _checkbox_item(True))
        layout.addWidget(self.table)

    def set_active_materials(self, active_materials: tuple[str, ...] | list[str]) -> None:
        self._active_summary.setText(_active_material_text(tuple(active_materials)))

    def collect(self) -> StabilityFlowInput:
        specimens: list[StabilitySpecimen] = []
        for r in range(self.table.rowCount()):
            data_cols = (0, 2, 3, 4, 5, 6, 7, 8)
            if not _row_has_any(self.table, r, data_cols):
                continue
            pb = _require_table_num(self.table, r, 0, f"Stability/Flow row {r + 1} Pb %")
            sid = _cell_text(self.table, r, 1) or f"S-{r + 1}"
            h = (
                _require_table_num(self.table, r, 2, f"Stability/Flow row {r + 1} H1"),
                _require_table_num(self.table, r, 3, f"Stability/Flow row {r + 1} H2"),
                _require_table_num(self.table, r, 4, f"Stability/Flow row {r + 1} H3"),
            )
            dia = _require_table_num(self.table, r, 5, f"Stability/Flow row {r + 1} diameter")
            corr = _require_table_num(self.table, r, 6, f"Stability/Flow row {r + 1} correction factor")
            stab = _require_table_num(self.table, r, 7, f"Stability/Flow row {r + 1} measured stability")
            flow = _require_table_num(self.table, r, 8, f"Stability/Flow row {r + 1} flow")
            override = _optional_table_num(self.table, r, 9, f"Stability/Flow row {r + 1} N override")
            inc_stab = self.table.item(r, 10).checkState() == Qt.Checked
            inc_flow = self.table.item(r, 11).checkState() == Qt.Checked
            specimens.append(StabilitySpecimen(
                bitumen_pct=pb, sample_id=sid,
                height_readings_mm=h, diameter_mm=dia,
                correction_factor=corr, measured_stability_kn=stab,
                flow_mm=flow,
                include_in_stab_avg=inc_stab,
                include_in_flow_avg=inc_flow,
                corrected_stability_kn_override=override,
            ))
        if not specimens:
            raise ValueError("Missing stability/flow data. Fill at least one complete specimen row before computing.")
        return StabilityFlowInput(specimens=tuple(specimens))


# ---------- Material Calculation tab --------------------------------------

class MaterialCalcTab(QWidget):
    """Inputs for the Material Calculation sheet: 3 numbers.

    The dry-material breakdown uses the blend ratios from the Gradation tab,
    so they don't need to be re-entered here.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(QLabel(
            "<b>Material Calculation for Preparation of Bituminous Mix Sample</b><br>"
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Enter the standard and target sample values manually. "
            "Dry-material breakdown uses only active Gradation-tab blend ratios."
            "</span>"
        ))
        self._active_summary = QLabel(_active_material_text(AGGS))
        self._active_summary.setStyleSheet("color:#4a5260; font-size:9pt;")
        layout.addWidget(self._active_summary)

        form_row = QHBoxLayout()

        self.std_pb = QLineEdit()
        self.std_pb.setValidator(QDoubleValidator(0.0, 20.0, 2, self))
        form_row.addWidget(QLabel("Standard Bitumen Content:"))
        form_row.addWidget(self.std_pb)

        self.std_agg_wt = QLineEdit()
        self.std_agg_wt.setValidator(QDoubleValidator(0.0, 100000.0, 1, self))
        form_row.addWidget(QLabel("Standard Aggregate Weight:"))
        form_row.addWidget(self.std_agg_wt)

        self.tgt_pb = QLineEdit()
        self.tgt_pb.setValidator(QDoubleValidator(0.0, 20.0, 2, self))
        form_row.addWidget(QLabel("Target Bitumen Content:"))
        form_row.addWidget(self.tgt_pb)

        form_row.addStretch(1)
        layout.addLayout(form_row)
        layout.addStretch(1)

    def set_active_materials(self, active_materials: tuple[str, ...] | list[str]) -> None:
        self._active_summary.setText(_active_material_text(tuple(active_materials)))

    def collect(self, blend_ratios: dict[str, float]) -> MaterialCalcInput:
        return MaterialCalcInput(
            standard_bitumen_pct=_line_num(self.std_pb, "standard bitumen content"),
            standard_aggregate_weight_g=_line_num(self.std_agg_wt, "standard aggregate weight"),
            target_bitumen_pct=_line_num(self.tgt_pb, "target bitumen content"),
            blend_ratios=dict(blend_ratios),
        )


# ---------- combined inputs panel -----------------------------------------

class InputsPanel(QWidget):
    """Hosts the 5 tabs. Provides .collect() returning all engine inputs."""

    compute_requested = Signal()
    reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PageHeader(
            "Mix Design Inputs",
            "Edit lab data per tab, then click Compute to run the engine.",
        )
        self.btn_compute = styled_button("Compute Mix Design")
        self.btn_compute.clicked.connect(self.compute_requested.emit)
        self.btn_reset = styled_button("Reset Inputs", "secondary")
        self.btn_reset.clicked.connect(self.reset_requested.emit)
        header.add_action(self.btn_reset)
        header.add_action(self.btn_compute)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tab_gradation = GradationTab()
        self.tab_spgr = SpGrTab()
        self.tab_gmb = GmbTab()
        self.tab_gmm = GmmTab()
        self.tab_sf = StabilityFlowTab()
        self.tab_material = MaterialCalcTab()
        for tab in (self.tab_spgr, self.tab_gmb, self.tab_gmm, self.tab_sf, self.tab_material):
            self.tab_gradation.active_materials_changed.connect(tab.set_active_materials)
            tab.set_active_materials(self.tab_gradation.active_materials())
        self.tabs.addTab(self.tab_gradation, "1. Gradation")
        self.tabs.addTab(self.tab_spgr, "2. Specific Gravity")
        self.tabs.addTab(self.tab_gmb, "3. Gmb")
        self.tabs.addTab(self.tab_gmm, "4. Gmm")
        self.tabs.addTab(self.tab_sf, "5. Stability / Flow")
        self.tabs.addTab(self.tab_material, "6. Material Calc")
        layout.addWidget(self.tabs, stretch=1)

    def set_mix_type(self, mix_type_key: str) -> None:
        """Drive the inputs panel from a selected mix type (F1).

        Forwards to the gradation tab which rebuilds its sieve set,
        envelope and placeholder warning from MIX_TYPES.
        """
        self.tab_gradation.set_mix_type(mix_type_key)

    def collect_all(self):
        grad = self.tab_gradation.collect()
        active_materials = tuple(grad.blend_ratios.keys())
        self.tab_spgr.set_active_materials(active_materials)
        coarse, fine, bit = self.tab_spgr.collect(active_materials)
        gmb = self.tab_gmb.collect()
        design_pbs = tuple(group.bitumen_pct for group in gmb.groups)
        gmm = self.tab_gmm.collect(bitumen_sg=0.0, design_pb_pct=design_pbs)
        stability_flow = self.tab_sf.collect()
        sf_pbs = {sp.bitumen_pct for sp in stability_flow.specimens}
        missing_sf = [pb for pb in design_pbs if pb not in sf_pbs]
        if missing_sf:
            raise ValueError(
                "Missing Stability/Flow rows for design bitumen content(s): "
                + ", ".join(f"{pb:g}%" for pb in missing_sf)
                + ". Fill matching Stability/Flow data before computing."
            )
        return {
            "gradation": grad,
            "spgr": (coarse, fine, bit),
            "gmb": gmb,
            "gmm": gmm,
            "stability_flow": stability_flow,
            "material_calc": self.tab_material.collect(dict(grad.blend_ratios)),
        }
