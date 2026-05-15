"""Tabbed inputs panel: Gradation | Sp.Gr. | Gmb | Gmm | Stability/Flow.

All inputs live in one widget so the engine receives a single coherent
payload when the user hits "Compute". Each tab is a QTableWidget with
sensible defaults pre-loaded from the source Excel sample.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
    MIX_TYPES,
    StabilityFlowInput,
    StabilitySpecimen,
)
from .common import PageHeader, styled_button


# Demo defaults are DBM-II-shaped — used only as fallback when no mix_type
# is supplied. F1 (dynamic gradation) drives the panel from MIX_TYPES at
# runtime via GradationTab.set_mix_type / InputsPanel.set_mix_type.
SIEVES = (37.5, 26.5, 19, 13.2, 4.75, 2.36, 0.3, 0.075)
AGGS = ("25mm", "20mm", "6mm", "SD", "Cement")
DESIGN_PB = (3.5, 4.0, 4.5, 5.0, 5.5)


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


# ---------- demo defaults from the Shirdi DBM dataset ---------------------

DEMO_GRADATION_PASS = {
    "25mm":   (100, 96.566, 44.500, 4.013, 0.000, 0.000, 0.000, 0.000),
    "20mm":   (100, 100,    89.832, 5.154, 0.000, 0.000, 0.000, 0.000),
    "6mm":    (100, 100,    100,    100,   38.600, 8.050, 0.000, 0.000),
    "SD":     (100, 100,    100,    100,   99.749, 92.285, 33.768, 9.469),
    "Cement": (100, 100,    100,    100,   100,    100,    100,    42.169),
}
DEMO_BLEND = {"25mm": 0.23, "20mm": 0.11, "6mm": 0.32, "SD": 0.32, "Cement": 0.02}
DEMO_SPEC_LOW = (100, 90, 71, 56, 38, 28, 7, 2)
DEMO_SPEC_UP  = (100, 100, 95, 80, 54, 42, 21, 8)


# ---------- gradation tab --------------------------------------------------

class GradationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sieves: tuple[float, ...] = SIEVES
        self._aggs: tuple[str, ...] = AGGS
        self._mix_type_key: str = ""
        self._mix_code_label = QLabel("")
        self._mix_code_label.setStyleSheet(
            "color:#1f3a68; font-size:10pt; font-weight:bold;"
        )
        self._warning_banner = QLabel("")
        self._warning_banner.setWordWrap(True)
        self._warning_banner.setStyleSheet(
            "background:#fff4e0; color:#8a5a00; padding:8px 10px;"
            "border:1px solid #f0c97a; border-radius:4px; font-size:10pt;"
        )
        self._warning_banner.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._mix_code_label)
        layout.addWidget(self._warning_banner)

        # Blend ratios row (small)
        self._blend_form = QFormLayout()
        self.blend_spins: dict[str, QDoubleSpinBox] = {}
        self._blend_row_widget = QWidget()
        self._blend_row = QHBoxLayout(self._blend_row_widget)
        self._blend_row.setContentsMargins(0, 0, 0, 0)
        for name in self._aggs:
            sp = QDoubleSpinBox()
            sp.setDecimals(3)
            sp.setRange(0, 1)
            sp.setSingleStep(0.01)
            sp.setValue(DEMO_BLEND.get(name, 0))
            self.blend_spins[name] = sp
            self._blend_row.addWidget(QLabel(name))
            self._blend_row.addWidget(sp)
        self._blend_form.addRow("Blend Ratios (sum to 1.000):", self._blend_row_widget)
        layout.addLayout(self._blend_form)

        # Gradation table
        headers = ["IS Sieve (mm)"] + list(self._aggs) + ["MoRTH Lower", "MoRTH Upper"]
        self.table = QTableWidget(len(self._sieves), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r, sieve in enumerate(self._sieves):
            _set_text(self.table, r, 0, f"{sieve:g}")
            for ci, name in enumerate(self._aggs, start=1):
                _set_num(self.table, r, ci, DEMO_GRADATION_PASS[name][r], decimals=2)
            _set_num(self.table, r, len(self._aggs) + 1, DEMO_SPEC_LOW[r], decimals=0)
            _set_num(self.table, r, len(self._aggs) + 2, DEMO_SPEC_UP[r], decimals=0)
        layout.addWidget(self.table)

    def set_mix_type(self, mix_type_key: str) -> None:
        """Rebuild the gradation table from MIX_TYPES[mix_type_key].

        Replaces sieve set, lower/upper envelope from the spec database
        (Phase 6 source-tagged). Per-aggregate passing% cells are cleared
        because demo numbers are mix-specific. The blend ratios row keeps
        its current AGG column structure (renaming bins is deferred — F3).
        Surfaces the placeholder warning banner when status is unverified.
        """
        record = MIX_TYPES.get(mix_type_key) if mix_type_key else None
        if not record or not record.sieve_sizes_mm:
            # Fallback: leave the demo (DBM-II) shape in place
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
        src = record.applicable_code or "—"
        self._mix_code_label.setText(
            f"Mix: {record.mix_code} — {record.full_name}    •    Spec: {src}"
        )

        # Placeholder warning banner (F2)
        if (record.status or "").strip() == "placeholder_editable":
            self._warning_banner.setText(
                f"⚠ Spec limits and gradation envelope for {record.mix_code} "
                f"are not IRC-verified. Results are indicative — confirm against "
                f"the relevant IRC clause before adoption. (Source: "
                f"{record.applicable_code or 'unverified'})"
            )
            self._warning_banner.setVisible(True)
        else:
            self._warning_banner.setVisible(False)

        # Rebuild table with new sieve count
        headers = ["IS Sieve (mm)"] + list(self._aggs) + ["MoRTH Lower", "MoRTH Upper"]
        self.table.setRowCount(len(self._sieves))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for r, sieve in enumerate(self._sieves):
            _set_text(self.table, r, 0, f"{sieve:g}")
            for ci, _name in enumerate(self._aggs, start=1):
                # Clear per-aggregate cells — demo values are DBM-II-shaped
                self.table.setItem(r, ci, QTableWidgetItem(""))
            lo = lower[r] if r < len(lower) else None
            hi = upper[r] if r < len(upper) else None
            if lo is not None:
                _set_num(self.table, r, len(self._aggs) + 1, float(lo), decimals=0)
            else:
                self.table.setItem(r, len(self._aggs) + 1, QTableWidgetItem(""))
            if hi is not None:
                _set_num(self.table, r, len(self._aggs) + 2, float(hi), decimals=0)
            else:
                self.table.setItem(r, len(self._aggs) + 2, QTableWidgetItem(""))

    def collect(self) -> GradationInput:
        blend = {n: self.blend_spins[n].value() for n in self._aggs}
        pass_pct = {}
        for ci, name in enumerate(self._aggs, start=1):
            pass_pct[name] = tuple(_get_num(self.table, r, ci) for r in range(len(self._sieves)))
        spec_low = tuple(_get_num(self.table, r, len(self._aggs) + 1) for r in range(len(self._sieves)))
        spec_up = tuple(_get_num(self.table, r, len(self._aggs) + 2) for r in range(len(self._sieves)))
        return GradationInput(
            sieve_sizes_mm=tuple(self._sieves),
            pass_pct=pass_pct,
            blend_ratios=blend,
            spec_lower=spec_low,
            spec_upper=spec_up,
        )


# ---------- specific-gravity tab ------------------------------------------

class SpGrTab(QWidget):
    """5 mini-tables: 25mm, 20mm, 6mm, SD, Bitumen.  Each: 4 reps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # 25mm coarse
        layout.addWidget(QLabel("<b>Coarse Aggregate 25 mm  (Wire Basket / IS 2386-III)</b>"))
        self.coarse_25 = QTableWidget(4, 4)
        self.coarse_25.setVerticalHeaderLabels(["A — sample+container in water",
                                                "B — container in water",
                                                "C — SSD in air",
                                                "D — oven-dry in air"])
        self.coarse_25.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.coarse_25.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Demo defaults (only rep 1 from the source file)
        for r, val in enumerate([3647, 2363, 2003, 1954]):
            _set_num(self.coarse_25, r, 0, val, decimals=0)
        layout.addWidget(self.coarse_25)

        # 20mm coarse
        layout.addWidget(QLabel("<b>Coarse Aggregate 20 mm</b>"))
        self.coarse_20 = QTableWidget(4, 4)
        self.coarse_20.setVerticalHeaderLabels(["A", "B", "C", "D"])
        self.coarse_20.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.coarse_20.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, val in enumerate([3649, 2363, 2010, 1951]):
            _set_num(self.coarse_20, r, 0, val, decimals=0)
        layout.addWidget(self.coarse_20)

        # 6mm fine (pycnometer)
        layout.addWidget(QLabel("<b>Fine Aggregate 6 mm  (Pycnometer)</b>"))
        self.fine_6 = QTableWidget(4, 4)
        self.fine_6.setVerticalHeaderLabels(["W1 — empty",
                                             "W2 — + dry sample",
                                             "W3 — + dry sample + water",
                                             "W4 — + water"])
        self.fine_6.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.fine_6.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, val in enumerate([492, 834, 1655, 1435]):
            _set_num(self.fine_6, r, 0, val, decimals=0)
        layout.addWidget(self.fine_6)

        # Stone dust
        layout.addWidget(QLabel("<b>Stone Dust  (Pycnometer)</b>"))
        self.fine_sd = QTableWidget(4, 4)
        self.fine_sd.setVerticalHeaderLabels(["W1", "W2", "W3", "W4"])
        self.fine_sd.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.fine_sd.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, val in enumerate([486, 839, 1664, 1439]):
            _set_num(self.fine_sd, r, 0, val, decimals=0)
        layout.addWidget(self.fine_sd)

        # Bitumen
        layout.addWidget(QLabel("<b>Bitumen VG-30  (Sp. Gr. Bottle)</b>"))
        self.bitumen = QTableWidget(4, 4)
        self.bitumen.setVerticalHeaderLabels(["A — empty bottle",
                                              "B — bottle + water",
                                              "C — bottle + sample",
                                              "D — bottle + sample + water"])
        self.bitumen.setHorizontalHeaderLabels(["Rep 1", "Rep 2", "Rep 3", "Rep 4"])
        self.bitumen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, val in enumerate([40.76, 97.5, 65.56, 97.77]):
            _set_num(self.bitumen, r, 0, val, decimals=2)
        layout.addWidget(self.bitumen)

    def _collect_coarse(self, t: QTableWidget) -> CoarseAggSGInput:
        cols = t.columnCount()
        def col(i):  # noqa
            return tuple(_get_num(t, r, c) for c in range(cols) for r in [i] if _get_num(t, r, c) != 0)
        # Simpler: iterate columns, skipping empty ones
        A = tuple(v for v in (_get_num(t, 0, c) for c in range(cols)) if v != 0)
        B = tuple(v for v in (_get_num(t, 1, c) for c in range(cols)) if v != 0)
        C = tuple(v for v in (_get_num(t, 2, c) for c in range(cols)) if v != 0)
        D = tuple(v for v in (_get_num(t, 3, c) for c in range(cols)) if v != 0)
        n = min(len(A), len(B), len(C), len(D))
        return CoarseAggSGInput(A[:n], B[:n], C[:n], D[:n])

    def _collect_fine(self, t: QTableWidget) -> FineAggSGInput:
        cols = t.columnCount()
        W1 = tuple(v for v in (_get_num(t, 0, c) for c in range(cols)) if v != 0)
        W2 = tuple(v for v in (_get_num(t, 1, c) for c in range(cols)) if v != 0)
        W3 = tuple(v for v in (_get_num(t, 2, c) for c in range(cols)) if v != 0)
        W4 = tuple(v for v in (_get_num(t, 3, c) for c in range(cols)) if v != 0)
        n = min(len(W1), len(W2), len(W3), len(W4))
        return FineAggSGInput(W1[:n], W2[:n], W3[:n], W4[:n])

    def collect(self) -> tuple[dict, dict, BitumenSGInput]:
        coarse = {"25mm": self._collect_coarse(self.coarse_25),
                  "20mm": self._collect_coarse(self.coarse_20)}
        fine = {"6mm": self._collect_fine(self.fine_6),
                "SD": self._collect_fine(self.fine_sd)}
        t = self.bitumen
        cols = t.columnCount()
        A = tuple(v for v in (_get_num(t, 0, c) for c in range(cols)) if v != 0)
        B = tuple(v for v in (_get_num(t, 1, c) for c in range(cols)) if v != 0)
        C = tuple(v for v in (_get_num(t, 2, c) for c in range(cols)) if v != 0)
        D = tuple(v for v in (_get_num(t, 3, c) for c in range(cols)) if v != 0)
        n = min(len(A), len(B), len(C), len(D))
        bit = BitumenSGInput(A[:n], B[:n], C[:n], D[:n])
        return coarse, fine, bit


# ---------- Gmb tab --------------------------------------------------------

GMB_DEMO_BY_PB = {
    3.5: [(1233, 732, 1236), (1231, 730, 1234), (1232, 729, 1234)],
    4.0: [(1239, 740, 1245), (1246, 741, 1249), (1247, 741, 1250)],
    4.5: [(1241, 741, 1245), (1247, 742, 1249), (1248, 743, 1251)],
    5.0: [(1241, 736, 1243), (1239, 735, 1242), (1241, 736, 1243)],
    5.5: [(1241, 736, 1246), (1245, 736, 1247), (1243, 735, 1245)],
}


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
        self.table = QTableWidget(len(GMB_DEMO_BY_PB) * 3, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        r = 0
        for pb, samples in GMB_DEMO_BY_PB.items():
            for s_idx, (A, C, B) in enumerate(samples, start=1):
                _set_text(self.table, r, 0, f"{pb:.1f}")
                _set_text(self.table, r, 1, f"S-{s_idx}")
                _set_num(self.table, r, 2, A, decimals=0)
                _set_num(self.table, r, 3, C, decimals=0)
                _set_num(self.table, r, 4, B, decimals=0)
                r += 1
        layout.addWidget(self.table)

    def collect(self) -> GmbInput:
        groups: dict[float, list[GmbSpecimen]] = {}
        order: list[float] = []
        for r in range(self.table.rowCount()):
            pb = float(self.table.item(r, 0).text())
            A = _get_num(self.table, r, 2)
            C = _get_num(self.table, r, 3)
            B = _get_num(self.table, r, 4)
            sp = GmbSpecimen(a_dry_in_air=A, c_in_water=C, b_ssd_in_air=B)
            if pb not in groups:
                groups[pb] = []
                order.append(pb)
            groups[pb].append(sp)
        return GmbInput(groups=tuple(
            GmbGroup(bitumen_pct=pb, specimens=tuple(groups[pb])) for pb in order
        ))


# ---------- Gmm tab --------------------------------------------------------

GMM_DEMO = [
    (909, 2152, 3316, 4072),
    (910, 2154, 3313, 4068),
]


class GmmTab(QWidget):
    """Reference Pb Rice test (2 samples) + design Pb list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(QLabel("<b>Reference Pb for Rice test</b>"))
        row = QHBoxLayout()
        self.pb_ref = QDoubleSpinBox()
        self.pb_ref.setDecimals(2); self.pb_ref.setRange(0, 20); self.pb_ref.setValue(4.5)
        row.addWidget(QLabel("Pb_ref (%)"))
        row.addWidget(self.pb_ref)
        row.addStretch(1)
        layout.addLayout(row)

        headers = ["Sample", "A — empty flask", "B — flask + dry sample",
                   "D — flask + water", "E — flask + sample + water"]
        self.table = QTableWidget(2, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        for r, (A, B, D, E) in enumerate(GMM_DEMO):
            _set_text(self.table, r, 0, f"S-{r+1}")
            _set_num(self.table, r, 1, A, decimals=0)
            _set_num(self.table, r, 2, B, decimals=0)
            _set_num(self.table, r, 3, D, decimals=0)
            _set_num(self.table, r, 4, E, decimals=0)
        layout.addWidget(self.table)

    def collect(self, bitumen_sg: float) -> GmmInput:
        samples = tuple(
            GmmSampleRaw(
                a_empty_flask=_get_num(self.table, r, 1),
                b_flask_plus_dry_sample=_get_num(self.table, r, 2),
                d_flask_filled_water=_get_num(self.table, r, 3),
                e_flask_sample_water=_get_num(self.table, r, 4),
            )
            for r in range(self.table.rowCount())
        )
        return GmmInput(
            reference_pb_pct=self.pb_ref.value(),
            samples_at_reference=samples,
            design_pb_pct=DESIGN_PB,
            bitumen_sg=bitumen_sg,
        )


# ---------- Stability/Flow tab --------------------------------------------

SF_DEMO_BY_PB = {
    3.5: [(64, 64, 63.6, 101.9, 1.00, 13.42, 3.21, 12.30),
          (64.05, 64, 65, 101.5, 1.00, 13.69, 3.32, 12.12),
          (65.71, 65.8, 66.83, 101.73, 0.93, 13.53, 3.55, 12.24)],
    4.0: [(65.04, 65.03, 65.09, 101.78, 0.96, 14.28, 3.41, None),
          (64.7, 64.32, 64.6, 101.3, 1.00, 14.16, 3.52, None),
          (64.72, 64.88, 64.52, 101.82, 0.96, 14.82, 3.38, None)],
    4.5: [(62.82, 62.84, 62.4, 101.84, 1.00, 16.33, 3.61, None),
          (64.33, 64.54, 64.02, 101.83, 0.96, 16.52, 3.66, None),
          (63.01, 63.44, 63.3, 101.73, 1.00, 16.58, 3.59, None)],
    5.0: [(64.1, 64.09, 64.2, 101.3, 1.00, 14.31, 3.78, None),
          (62.2, 62.29, 62.15, 101.4, 1.04, 14.22, 3.69, None),
          (62.35, 62.15, 63, 101.2, 1.04, 13.65, 3.81, None)],
    5.5: [(62.15, 62.8, 62.78, 101.6, 1.04, 12.76, 3.86, None),
          (62.79, 62.4, 62.7, 101.19, 1.04, 12.7, 3.83, None),
          (63.2, 62.7, 62.5, 102.3, 1.00, 14.28, 3.96, None)],
}


class StabilityFlowTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel(
            "<b>Marshall Stability and Flow</b>  "
            "(per-specimen include columns let you exclude failed-height samples)"
        ))
        headers = [
            "Pb %", "Sample", "H1", "H2", "H3", "Dia mm", "Corr. Factor",
            "Measured Stab. (kN)", "Flow (mm)", "N override (opt)",
            "Inc Stab", "Inc Flow",
        ]
        rows = sum(len(v) for v in SF_DEMO_BY_PB.values())
        self.table = QTableWidget(rows, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        r = 0
        for pb, samples in SF_DEMO_BY_PB.items():
            for s_idx, (h1, h2, h3, dia, corr, stab, flow, n_override) in enumerate(samples, start=1):
                _set_text(self.table, r, 0, f"{pb:.1f}")
                _set_text(self.table, r, 1, f"S-{s_idx}")
                _set_num(self.table, r, 2, h1, decimals=2)
                _set_num(self.table, r, 3, h2, decimals=2)
                _set_num(self.table, r, 4, h3, decimals=2)
                _set_num(self.table, r, 5, dia, decimals=2)
                _set_num(self.table, r, 6, corr, decimals=2)
                _set_num(self.table, r, 7, stab, decimals=2)
                _set_num(self.table, r, 8, flow, decimals=2)
                if n_override is not None:
                    _set_num(self.table, r, 9, n_override, decimals=2)
                else:
                    self.table.setItem(r, 9, QTableWidgetItem(""))
                self.table.setItem(r, 10, _checkbox_item(True))
                self.table.setItem(r, 11, _checkbox_item(True))
                r += 1
        layout.addWidget(self.table)

    def collect(self) -> StabilityFlowInput:
        specimens: list[StabilitySpecimen] = []
        for r in range(self.table.rowCount()):
            pb = float(self.table.item(r, 0).text())
            sid = self.table.item(r, 1).text()
            h = (_get_num(self.table, r, 2), _get_num(self.table, r, 3),
                 _get_num(self.table, r, 4))
            dia = _get_num(self.table, r, 5)
            corr = _get_num(self.table, r, 6)
            stab = _get_num(self.table, r, 7)
            flow = _get_num(self.table, r, 8)
            override_item = self.table.item(r, 9)
            override = (
                float(override_item.text())
                if override_item and override_item.text().strip() else None
            )
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
            "Two parallel blocks reproduced from Excel sheet \"Material  Cal\": "
            "a Standard sample at a chosen Pb (default 4.5 %, agg = 1200 g), "
            "and a Target sample scaled to that standard's total mix weight. "
            "Dry-material breakdown uses the Gradation-tab blend ratios."
            "</span>"
        ))

        form_row = QHBoxLayout()

        self.std_pb = QDoubleSpinBox()
        self.std_pb.setDecimals(2); self.std_pb.setRange(0, 20); self.std_pb.setValue(4.5)
        self.std_pb.setSuffix(" %")
        form_row.addWidget(QLabel("Standard Bitumen Content:"))
        form_row.addWidget(self.std_pb)

        self.std_agg_wt = QDoubleSpinBox()
        self.std_agg_wt.setDecimals(1); self.std_agg_wt.setRange(0, 100000)
        self.std_agg_wt.setValue(1200.0); self.std_agg_wt.setSuffix(" g")
        form_row.addWidget(QLabel("Standard Aggregate Weight:"))
        form_row.addWidget(self.std_agg_wt)

        self.tgt_pb = QDoubleSpinBox()
        self.tgt_pb.setDecimals(2); self.tgt_pb.setRange(0, 20); self.tgt_pb.setValue(4.0)
        self.tgt_pb.setSuffix(" %")
        form_row.addWidget(QLabel("Target Bitumen Content:"))
        form_row.addWidget(self.tgt_pb)

        form_row.addStretch(1)
        layout.addLayout(form_row)
        layout.addStretch(1)

    def collect(self, blend_ratios: dict[str, float]) -> MaterialCalcInput:
        return MaterialCalcInput(
            standard_bitumen_pct=self.std_pb.value(),
            standard_aggregate_weight_g=self.std_agg_wt.value(),
            target_bitumen_pct=self.tgt_pb.value(),
            blend_ratios=dict(blend_ratios),
        )


# ---------- combined inputs panel -----------------------------------------

class InputsPanel(QWidget):
    """Hosts the 5 tabs. Provides .collect() returning all engine inputs."""

    compute_requested = Signal()
    load_demo_requested = Signal()

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
        self.btn_demo = styled_button("Reset to Demo Data", "secondary")
        self.btn_demo.clicked.connect(self.load_demo_requested.emit)
        header.add_action(self.btn_demo)
        header.add_action(self.btn_compute)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tab_gradation = GradationTab()
        self.tab_spgr = SpGrTab()
        self.tab_gmb = GmbTab()
        self.tab_gmm = GmmTab()
        self.tab_sf = StabilityFlowTab()
        self.tab_material = MaterialCalcTab()
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
        return {
            "gradation": grad,
            "spgr": self.tab_spgr.collect(),
            "gmb": self.tab_gmb.collect(),
            "gmm_tab": self.tab_gmm,
            "stability_flow": self.tab_sf.collect(),
            "material_calc": self.tab_material.collect(dict(grad.blend_ratios)),
        }
