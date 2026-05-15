"""Specification Database / Admin — view & edit mix-type Marshall criteria.

Read-only fields: category, layer type, NMAS, applicable code.
Editable: the 11 Marshall criteria (when present).  Save writes back to
``%LOCALAPPDATA%\\PavementLab\\mix_specs.json`` (user override) and calls
``reload_specs()`` so the change is live without restart.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import MIX_TYPES, MixTypeRecord, reload_specs, save_specs
from .common import Card, PageHeader, styled_button


CATEGORY_LABELS = {
    "hot_mix":         ("Hot Mix",         "#1f3a68", "#e3eaf6"),
    "surface_course":  ("Surface Course",  "#8a5a00", "#fbeed5"),
    "maintenance":     ("Maintenance",     "#1d7a3a", "#dbf0e2"),
    "recycling":       ("Recycling",       "#5e2a99", "#e8dcf7"),
}
STATUS_LABELS = {
    "verified":             ("Verified",    "#1d7a3a", "#dbf0e2"),
    "placeholder_editable": ("Placeholder", "#a06d00", "#fbf2d3"),
}


def _badge(text: str, fg: str, bg: str) -> str:
    return (
        f'<span style="background:{bg}; color:{fg}; '
        f'padding:2px 8px; border-radius:9px; font-size:9pt; '
        f'font-weight:bold;">{text}</span>'
    )


class MarshallEditDialog(QDialog):
    """Form to edit the 11 Marshall criteria for one MixTypeRecord."""

    def __init__(self, rec: MixTypeRecord, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Marshall Criteria — {rec.mix_code}")
        self.setMinimumWidth(440)
        self.rec = deepcopy(rec)
        m = self.rec.marshall or {}

        lay = QVBoxLayout(self)
        info = QLabel(
            f"<b>{rec.full_name}</b> &nbsp;·&nbsp; "
            f"<span style='color:#6a7180;'>Code: {rec.applicable_code or '—'}</span>"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        form.setSpacing(6)
        self._spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        for key, label, lo, hi, step, decimals, default in (
            ("stability_min_kn",         "Stability min (kN)",      0, 50, 0.1, 2, 9.0),
            ("flow_min_mm",              "Flow min (mm)",           0, 10, 0.1, 2, 2.0),
            ("flow_max_mm",              "Flow max (mm)",           0, 10, 0.1, 2, 4.0),
            ("air_voids_min_pct",        "Air voids min (%)",       0, 20, 0.1, 2, 3.0),
            ("air_voids_max_pct",        "Air voids max (%)",       0, 20, 0.1, 2, 5.0),
            ("vma_min_pct",              "VMA min (%)",             0, 40, 0.05, 2, 13.0),
            ("vfb_min_pct",              "VFB min (%)",             0, 100, 0.5, 1, 65.0),
            ("vfb_max_pct",              "VFB max (%)",             0, 100, 0.5, 1, 75.0),
            ("marshall_quotient_min",    "Marshall Quotient min",   0, 20, 0.1, 2, 2.0),
            ("marshall_quotient_max",    "Marshall Quotient max",   0, 20, 0.1, 2, 5.0),
        ):
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
            sp.setValue(float(m.get(key, default)))
            self._spins[key] = sp
            form.addRow(label, sp)

        blows = QSpinBox()
        blows.setRange(0, 200); blows.setValue(int(m.get("compaction_blows_each_face", 75)))
        self._spins["compaction_blows_each_face"] = blows
        form.addRow("Compaction blows / face", blows)

        # Status combo
        self._status = QComboBox()
        self._status.addItems(["verified", "placeholder_editable"])
        i = self._status.findText(rec.status)
        self._status.setCurrentIndex(i if i >= 0 else 1)
        form.addRow("Status", self._status)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def updated_record(self) -> MixTypeRecord:
        m = {}
        for k, w in self._spins.items():
            m[k] = w.value()
        self.rec.marshall = m
        self.rec.status = self._status.currentText()
        return self.rec


class SpecAdminPanel(QWidget):
    """Table of all mix types in MIX_TYPES, with Edit Marshall for those that have it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.header = PageHeader(
            "Specification Database",
            "Mix-type registry — view, edit Marshall limits, mark verified vs placeholder."
        )
        self.btn_reload = styled_button("Reload from disk", "secondary")
        self.btn_reload.clicked.connect(self._on_reload)
        self.header.add_action(self.btn_reload)
        lay.addWidget(self.header)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16); bl.setSpacing(12)

        # Filter bar
        flt = QHBoxLayout()
        flt.setSpacing(8)
        flt.addWidget(QLabel("Filter category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItem("(all)", None)
        for key in CATEGORY_LABELS:
            self.cat_combo.addItem(CATEGORY_LABELS[key][0], key)
        self.cat_combo.currentIndexChanged.connect(self.refresh)
        flt.addWidget(self.cat_combo)
        flt.addStretch(1)
        bl.addLayout(flt)

        # Spec table
        card = Card()
        cl = QVBoxLayout(card); cl.setContentsMargins(14, 12, 14, 12)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Mix Code", "Full Name", "Category", "NMAS (mm)", "Status", ""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 130)
        self.table.verticalHeader().setVisible(False)
        cl.addWidget(self.table)
        bl.addWidget(card, stretch=1)

        # Footer hint
        bl.addWidget(QLabel(
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Edits are saved to <code>%LOCALAPPDATA%\\PavementLab\\mix_specs.json</code> "
            "(your personal override). The bundled defaults are never modified."
            "</span>"))

        lay.addWidget(body, stretch=1)

    def refresh(self) -> None:
        cat_filter = self.cat_combo.currentData()
        records = [r for r in MIX_TYPES.values()
                   if cat_filter is None or r.category == cat_filter]
        records.sort(key=lambda r: (r.category, r.mix_code))
        self.table.setRowCount(len(records))
        for r, rec in enumerate(records):
            self.table.setItem(r, 0, QTableWidgetItem(rec.mix_code))
            self.table.setItem(r, 1, QTableWidgetItem(rec.full_name))

            cat_label, cat_fg, cat_bg = CATEGORY_LABELS.get(
                rec.category, (rec.category, "#6a7180", "#eef0f4")
            )
            cat_lbl = QLabel(_badge(cat_label, cat_fg, cat_bg))
            cat_lbl.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(r, 2, cat_lbl)

            self.table.setItem(r, 3, QTableWidgetItem(
                f"{rec.nmas_mm:g}" if rec.nmas_mm else "—"))

            st_label, st_fg, st_bg = STATUS_LABELS.get(
                rec.status, (rec.status, "#6a7180", "#eef0f4")
            )
            st_lbl = QLabel(_badge(st_label, st_fg, st_bg))
            st_lbl.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(r, 4, st_lbl)

            for c in (0, 1, 3):
                if self.table.item(r, c):
                    self.table.item(r, c).setTextAlignment(Qt.AlignCenter)

            if rec.marshall is not None:
                btn = QPushButton("Edit Marshall")
                btn.setStyleSheet(
                    "background:#1f3a68; color:white; border:none; "
                    "padding:4px 10px; border-radius:3px; font-size:9pt;"
                )
                btn.clicked.connect(lambda _=False, code=rec.mix_code: self._edit(code))
                self.table.setCellWidget(r, 5, btn)
            else:
                lbl = QLabel("<i style='color:#6a7180;'>no Marshall block</i>")
                lbl.setAlignment(Qt.AlignCenter)
                self.table.setCellWidget(r, 5, lbl)

    def _edit(self, code: str) -> None:
        rec = MIX_TYPES.get(code)
        if rec is None:
            return
        dlg = MarshallEditDialog(rec, self)
        if dlg.exec() == QDialog.Accepted:
            updated = dlg.updated_record()
            # Write user-override JSON
            try:
                path = save_specs({code: updated})
                reload_specs()
                self.refresh()
                QMessageBox.information(self, "Saved",
                    f"{code} Marshall criteria saved to:\n{path}")
            except Exception as e:                              # pragma: no cover
                QMessageBox.critical(self, "Save failed", str(e))

    def _on_reload(self) -> None:
        n_specs, n_total = reload_specs()
        self.refresh()
        QMessageBox.information(self, "Reloaded",
            f"Loaded {n_total} mix types ({n_specs} with Marshall criteria).")
