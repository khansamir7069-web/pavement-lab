"""Results: summary table + OBC + compliance + charts + report buttons."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from app.core import MaterialCalcResult, MixDesignResult, MIX_TYPES
from app.core.import_summary import ImportedMixResult
from app.graphs import build_chart_set, render_chart_to_axes
from .common import Card, PageHeader, PlaceholderBanner, styled_button


class ResultsPanel(QWidget):
    generate_word = Signal()
    generate_pdf = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: MixDesignResult | None = None
        self._material: MaterialCalcResult | None = None
        self._mix_type_key: str = ""
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PageHeader("Results & Report",
                            "Marshall summary, OBC, compliance and Word export.")
        self.btn_word = styled_button("Export Word")
        self.btn_word.clicked.connect(self.generate_word.emit)
        # PDF export is hidden in Phase 6 — Word-only output is the
        # supported deliverable. The engine in word_report.export_to_pdf()
        # stays available for ad-hoc conversion.
        self.btn_pdf = styled_button("Export PDF", "secondary")
        self.btn_pdf.clicked.connect(self.generate_pdf.emit)
        self.btn_pdf.setVisible(False)
        header.add_action(self.btn_pdf)
        header.add_action(self.btn_word)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(14)
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        # F2 placeholder warning banner — surfaces placeholder_editable status
        self.lbl_placeholder_warning = PlaceholderBanner()
        body_layout.addWidget(self.lbl_placeholder_warning)

        # OBC card
        self.obc_card = Card()
        obc_layout = QGridLayout(self.obc_card)
        obc_layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Optimum Bitumen Content")
        title.setStyleSheet("color:#1f3a68; font-size:13pt; font-weight:bold;")
        obc_layout.addWidget(title, 0, 0, 1, 4)
        self.lbl_obc = QLabel("—")
        self.lbl_obc.setStyleSheet("font-size:28pt; font-weight:bold; color:#1d7a3a;")
        obc_layout.addWidget(self.lbl_obc, 1, 0)
        self.lbl_obc_meta = QLabel("Compute the mix design to see results.")
        self.lbl_obc_meta.setStyleSheet("color:#6a7180; font-size:10pt;")
        obc_layout.addWidget(self.lbl_obc_meta, 1, 1, 1, 3)
        body_layout.addWidget(self.obc_card)

        # Summary table card
        summary_card = Card()
        sl = QVBoxLayout(summary_card)
        sl.setContentsMargins(20, 16, 20, 16)
        sl.addWidget(QLabel("<b>Marshall Mix Design Summary</b>"))
        self.summary_table = QTableWidget(0, 9)
        self.summary_table.setHorizontalHeaderLabels(
            ["Pb %", "Gmm", "Gmb", "VIM %", "VMA %", "VFB %",
             "Stab kN", "Flow mm", "MQ"])
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary_table.verticalHeader().setVisible(False)
        sl.addWidget(self.summary_table)
        body_layout.addWidget(summary_card)

        # Compliance card
        comp_card = Card()
        cl = QVBoxLayout(comp_card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.addWidget(QLabel("<b>Specification Compliance at OBC</b>"))
        self.comp_table = QTableWidget(0, 4)
        self.comp_table.setHorizontalHeaderLabels(
            ["Property", "Value at OBC", "Requirement", "Status"])
        self.comp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comp_table.verticalHeader().setVisible(False)
        cl.addWidget(self.comp_table)
        self.lbl_compliance = QLabel("")
        self.lbl_compliance.setStyleSheet("font-size:13pt; font-weight:bold;")
        cl.addWidget(self.lbl_compliance)
        body_layout.addWidget(comp_card)

        # Material Calculation card
        self.material_card = Card()
        ml = QVBoxLayout(self.material_card)
        ml.setContentsMargins(20, 16, 20, 16)
        ml.addWidget(QLabel("<b>Material Calculation — Sample Preparation</b>"))
        ml.addWidget(QLabel(
            "<span style='color:#6a7180; font-size:9pt;'>"
            "Standard sample (left) and target Pb sample (right) with dry-material "
            "breakdown by aggregate fraction."
            "</span>"))
        self.material_summary_table = QTableWidget(0, 5)
        self.material_summary_table.setHorizontalHeaderLabels(
            ["Block", "Pb %", "Aggregate %", "Aggregate wt (g)", "Bitumen wt (g)"])
        self.material_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.material_summary_table.verticalHeader().setVisible(False)
        ml.addWidget(self.material_summary_table)
        self.material_total_label = QLabel("")
        self.material_total_label.setStyleSheet("color:#1f3a68; font-weight:bold; font-size:11pt;")
        ml.addWidget(self.material_total_label)

        dry_row = QHBoxLayout()
        self.material_std_table = QTableWidget(0, 3)
        self.material_std_table.setHorizontalHeaderLabels(["Fraction", "Ratio", "Weight (g)"])
        self.material_std_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.material_std_table.verticalHeader().setVisible(False)
        std_box = QVBoxLayout()
        std_box.addWidget(QLabel("<b>Standard sample — dry material</b>"))
        std_box.addWidget(self.material_std_table)

        self.material_tgt_table = QTableWidget(0, 3)
        self.material_tgt_table.setHorizontalHeaderLabels(["Fraction", "Ratio", "Weight (g)"])
        self.material_tgt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.material_tgt_table.verticalHeader().setVisible(False)
        tgt_box = QVBoxLayout()
        tgt_box.addWidget(QLabel("<b>Target sample — dry material</b>"))
        tgt_box.addWidget(self.material_tgt_table)

        dry_row.addLayout(std_box)
        dry_row.addLayout(tgt_box)
        ml.addLayout(dry_row)
        body_layout.addWidget(self.material_card)

        # Charts card
        chart_card = Card()
        chl = QVBoxLayout(chart_card)
        chl.setContentsMargins(20, 16, 20, 16)
        chl.addWidget(QLabel("<b>Marshall Design Curves</b>"))
        self.chart_grid = QGridLayout()
        chl.addLayout(self.chart_grid)
        body_layout.addWidget(chart_card)
        body_layout.addStretch(1)

    # ----------------------------------------------------------------

    def set_mix_type_key(self, mix_type_key: str) -> None:
        """Tell the panel which mix type the current result belongs to.

        Drives the F2 placeholder warning banner. Should be called before
        :meth:`set_result`; if not, the banner stays hidden.
        """
        self._mix_type_key = mix_type_key or ""
        self._refresh_placeholder_warning()

    def _refresh_placeholder_warning(self) -> None:
        rec = MIX_TYPES.get(self._mix_type_key) if self._mix_type_key else None
        if rec and (rec.status or "").strip() == "placeholder_editable":
            self.lbl_placeholder_warning.set_message(
                f"⚠ Spec limits for {rec.mix_code} ({rec.full_name}) are not "
                f"IRC-verified. Compliance verdict below is indicative only — "
                f"confirm against the relevant IRC clause before adoption. "
                f"(Source: {rec.applicable_code or 'unverified'})"
            )
        else:
            self.lbl_placeholder_warning.set_message("", visible=False)

    def set_result(self, result: "MixDesignResult | ImportedMixResult",
                   material: MaterialCalcResult | None = None) -> None:
        self._result = result
        self._material = material
        self._refresh_placeholder_warning()

        # OBC card
        self.lbl_obc.setText(f"{result.obc.obc_pct:.2f}%")
        self.lbl_obc_meta.setText(
            f"At target {result.obc.target_air_voids_pct:.1f}% air voids · "
            f"method: {result.obc.method.replace('_', ' ')} · "
            f"Gsb = {result.bulk_sg_blend:.3f} · "
            f"Gb = {result.bitumen_sg:.3f}"
        )

        # Summary table
        rows = result.summary.rows
        self.summary_table.setRowCount(len(rows))
        for r, mr in enumerate(rows):
            for c, val, dec in [
                (0, mr.bitumen_pct, 1),
                (1, mr.gmm, 3),
                (2, mr.gmb, 3),
                (3, mr.air_voids_pct, 2),
                (4, mr.vma_pct, 2),
                (5, mr.vfb_pct, 2),
                (6, mr.stability_kn, 2),
                (7, mr.flow_mm, 2),
                (8, mr.marshall_quotient, 2),
            ]:
                item = QTableWidgetItem(f"{val:.{dec}f}")
                item.setTextAlignment(Qt.AlignCenter)
                self.summary_table.setItem(r, c, item)

        # Compliance
        comp_items = list(result.compliance.items) + [
            ("Gmb at OBC", result.obc.gmb_at_obc, "—", None),
            ("Gmm at OBC", result.obc.gmm_at_obc, "—", None),
        ]
        self.comp_table.setRowCount(len(comp_items))
        for r, item in enumerate(comp_items):
            if hasattr(item, "name"):
                name, value, req, ok = item.name, item.value, item.requirement, item.pass_
            else:
                name, value, req, ok = item
            self.comp_table.setItem(r, 0, QTableWidgetItem(name))
            self.comp_table.setItem(r, 1, QTableWidgetItem(f"{value:.2f}" if isinstance(value, float) else str(value)))
            self.comp_table.setItem(r, 2, QTableWidgetItem(req))
            status_item = QTableWidgetItem(
                "—" if ok is None else ("PASS" if ok else "FAIL")
            )
            if ok is True:
                status_item.setBackground(QColor(220, 240, 226))
                status_item.setForeground(QColor(29, 122, 58))
            elif ok is False:
                status_item.setBackground(QColor(247, 220, 220))
                status_item.setForeground(QColor(192, 69, 69))
            self.comp_table.setItem(r, 3, status_item)
            for c in range(4):
                if self.comp_table.item(r, c):
                    self.comp_table.item(r, c).setTextAlignment(Qt.AlignCenter)

        overall = result.compliance.overall_pass
        self.lbl_compliance.setText(
            f"Overall ({result.compliance.spec_name}): "
            f"{'PASS ✓' if overall else 'FAIL ✗'}"
        )
        self.lbl_compliance.setStyleSheet(
            f"font-size:13pt; font-weight:bold; color:{'#1d7a3a' if overall else '#c04545'};"
        )

        # Material Calculation
        if material is not None:
            self._populate_material_card(material)
            self.material_card.setVisible(True)
        else:
            self.material_card.setVisible(False)

        # Charts
        for i in reversed(range(self.chart_grid.count())):
            w = self.chart_grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        cs = build_chart_set(result.summary, result.obc)
        for i, cd in enumerate(cs.charts):
            row, col = divmod(i, 2)
            fig = Figure(figsize=(4.5, 3.0), tight_layout=True)
            ax = fig.add_subplot(111)
            render_chart_to_axes(ax, cs, cd)
            ax.legend(loc="best", fontsize=8)
            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            canvas.setMinimumHeight(280)
            self.chart_grid.addWidget(canvas, row, col)

    def result(self) -> MixDesignResult | None:
        return self._result

    def material(self) -> MaterialCalcResult | None:
        return self._material

    def _populate_material_card(self, m: MaterialCalcResult) -> None:
        # Summary table
        rows = [
            ("Standard sample", m.standard.bitumen_pct, m.standard.aggregate_pct,
             m.standard.aggregate_weight_g, m.standard.bitumen_weight_g),
            ("Target sample",   m.target.bitumen_pct,   m.target.aggregate_pct,
             m.target.aggregate_weight_g, m.target.bitumen_weight_g),
        ]
        self.material_summary_table.setRowCount(len(rows))
        for r, (name, pb, agg, aw, bw) in enumerate(rows):
            for c, val, fmt in [
                (0, name, "{}"),
                (1, pb, "{:.2f}"),
                (2, agg, "{:.2f}"),
                (3, aw, "{:.2f}"),
                (4, bw, "{:.2f}"),
            ]:
                text = fmt.format(val) if not isinstance(val, str) else val
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.material_summary_table.setItem(r, c, item)

        self.material_total_label.setText(
            f"Total Bituminous Mix Weight (standard) = "
            f"{m.standard.total_mix_weight_g:.2f} g  ·  "
            f"Target Total = {m.target.total_mix_weight_g:.2f} g"
        )

        # Dry material tables
        for tbl, dry in [(self.material_std_table, m.dry_material_standard),
                         (self.material_tgt_table, m.dry_material_target)]:
            tbl.setRowCount(len(dry) + 1)
            total_w = 0.0
            for r, row in enumerate(dry):
                items = [
                    QTableWidgetItem(row.name),
                    QTableWidgetItem(f"{row.fraction * 100:.1f}%"),
                    QTableWidgetItem(f"{row.weight_g:.2f}"),
                ]
                for c, it in enumerate(items):
                    it.setTextAlignment(Qt.AlignCenter)
                    tbl.setItem(r, c, it)
                total_w += row.weight_g
            for c, txt in enumerate(["TOTAL", "100.0%", f"{total_w:.2f}"]):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                font = it.font(); font.setBold(True); it.setFont(font)
                tbl.setItem(len(dry), c, it)
