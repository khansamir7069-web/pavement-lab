"""Module Hub — grid of clickable module cards for the current project.

Each card represents a stage of the consultant-style workflow.
The hub shows per-stage status dropdowns and a Next Step Assistant banner.
"""
from __future__ import annotations

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QScrollArea,
)

from .common import Card, PageHeader

MODULES: tuple[tuple[str, str, str], ...] = (
    ("project",       "Project Setup",
        "Define project metadata, client name, standards, and life"),
    ("traffic",       "Traffic Survey / MSA",
        "IRC:37 — CVPD, VDF, LDF → design MSA & AASHTO ESAL"),
    ("subgrade",      "Subgrade / CBR",
        "IRC:37 — Evaluate subgrade resilient modulus (Mr) from CBR"),
    ("structural",    "Pavement Structural Design",
        "IRC:37 — Pavement layer thickness suggestion based on CBR & traffic"),
    ("stabilized",    "Alternative Selection",
        "IRC:37 — Design and compare stabilized pavement alternatives (CTB/CTS)"),
    ("iitpave_status", "IITPAVE Verification",
        "Verify pavement layer strains and fatigue/rutting life using IITPAVE"),
    ("mix_design",    "Bituminous Mix Design",
        "Marshall mix design (gradation, binder optimization)"),
    ("material_qty",  "BOQ",
        "Calculate quantities and costs for a road stretch (BOQ)"),
    ("engineering_review", "Engineering Review",
        "Conduct review checklists, QA validation checks, and notes"),
    ("submission",    "Submission",
        "Lock final project design and generate delivery package ZIP"),
)

STATUS_BADGE = {
    "empty":       ("Not started", "#6a7180", "#eef0f4"),
    "in_progress": ("● In progress", "#a06d00", "#fbf2d3"),
    "complete":    ("✓ Completed", "#1d7a3a", "#e0f2e7"),
    "needs_review":("⚠ Needs Review", "#d9381e", "#fde8e5"),
    "locked":      ("🔒 Locked", "#4a5568", "#edf2f7"),
}


class ModuleCard(Card):
    """Clickable card with title, description, and status dropdown."""

    def __init__(self, key: str, title: str, description: str, parent_hub: ModuleHub, parent=None):
        super().__init__(parent)
        self.key = key
        self.parent_hub = parent_hub
        self.setObjectName("ModuleCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(145)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(6)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(
            "font-size:12pt; font-weight:bold; color:#1f3a68;"
        )
        v.addWidget(self.title_lbl)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#6a7180; font-size:9pt;")
        v.addWidget(desc)
        v.addStretch(1)

        # Status dropdown combo box (restricted items)
        self.badge = QComboBox(self)
        self.badge.currentIndexChanged.connect(self._on_status_changed)
        v.addWidget(self.badge, 0, Qt.AlignLeft)

    def set_status(self, status: str) -> None:
        self.badge.blockSignals(True)
        self.badge.clear()

        # The Completed status is system-derived and cannot be manually selected.
        # We only add it to the dropdown options if the current status is complete.
        if status == "complete":
            self.badge.addItem("✓ Completed", "complete")

        self.badge.addItem("Not started", "empty")
        self.badge.addItem("In progress", "in_progress")
        self.badge.addItem("Needs Review", "needs_review")
        self.badge.addItem("Locked", "locked")

        idx = self.badge.findData(status)
        if idx >= 0:
            self.badge.setCurrentIndex(idx)
        else:
            self.badge.setCurrentIndex(0)

        # Style dropdown to look like a pill badge
        _, fg, bg = STATUS_BADGE.get(status, STATUS_BADGE["empty"])
        self.badge.setStyleSheet(
            f"QComboBox {{"
            f"  background: {bg}; color: {fg};"
            f"  font-size: 8pt; font-weight: bold; padding: 2px 12px; border-radius: 10px;"
            f"  border: 1px solid {fg}; min-width: 110px;"
            f"}}"
            f"QComboBox::drop-down {{"
            f"  border: none;"
            f"  width: 0px;"
            f"}}"
        )
        self.badge.blockSignals(False)

    def _on_status_changed(self, idx: int) -> None:
        status_key = self.badge.currentData()
        if status_key and self.parent_hub:
            self.parent_hub.status_changed.emit(self.key, status_key)

    def mousePressEvent(self, ev):
        # Only click card to navigate if not clicking the status combo box
        child = self.childAt(ev.position().toPoint())
        if child != self.badge:
            if ev.button() == Qt.LeftButton:
                self.parent_hub._emit(self.key)
        super().mousePressEvent(ev)


class ModuleHub(QWidget):
    module_selected = Signal(str)   # key
    status_changed = Signal(str, str) # key, status

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._project_name: str = ""
        self._cards: dict[str, ModuleCard] = {}
        self.db = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "Project Workspace",
            "Pick a module to work on. Sequence gates protect the engineering design workflow."
        )
        lay.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)
        body_lay.setSpacing(14)

        # Project banner
        self.proj_banner = QLabel("")
        self.proj_banner.setStyleSheet(
            "background:#eaf0fa; color:#1f3a68; padding:10px 14px; "
            "border:1px solid #c9d6ec; border-radius:4px; font-size:11pt;"
        )
        body_lay.addWidget(self.proj_banner)

        # Assistant banner
        self.assistant_card = Card()
        assistant_layout = QVBoxLayout(self.assistant_card)
        assistant_layout.setContentsMargins(14, 12, 14, 12)
        
        assistant_title = QLabel("⛏  Next Step Assistant")
        assistant_title.setStyleSheet("font-size:11pt; font-weight:bold; color:#1f3a68;")
        assistant_layout.addWidget(assistant_title)
        
        self.assistant_lbl = QLabel("Please load or create a project to start.")
        self.assistant_lbl.setWordWrap(True)
        self.assistant_lbl.setStyleSheet("color:#6a7180; font-size:10pt;")
        assistant_layout.addWidget(self.assistant_lbl)
        
        body_lay.addWidget(self.assistant_card)

        # Cards grid (3 columns)
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (key, title, desc) in enumerate(MODULES):
            card = ModuleCard(key, title, desc, self)
            self._cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        body_lay.addLayout(grid)
        body_lay.addStretch(1)

        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

    def _emit(self, key: str) -> None:
        self.module_selected.emit(key)

    def set_project(self, project_id: int | None, name: str,
                    module_status: dict | None = None, db = None) -> None:
        self._project_id = project_id
        self.db = db
        self._project_name = name or "(Unnamed Project)"
        
        if project_id is None:
            self.proj_banner.setText("No project selected.")
            self.assistant_lbl.setText("Please load or create a project to start.")
            for card in self._cards.values():
                card.badge.setEnabled(False)
        else:
            p = self.db.get_project(project_id) if self.db else None
            rev_num = p.revision_number if p else 0
            rev_text = f" (Revision #{rev_num})" if rev_num > 0 else ""
            self.proj_banner.setText(
                f"<b>Project #{project_id}:</b> {self._project_name}{rev_text}"
            )
            module_status = module_status or {}
            self._update_assistant(module_status)
            for key, card in self._cards.items():
                card.set_status(module_status.get(key, "empty"))
                # Disable status changing dropdowns if project is locked
                card.badge.setEnabled(not (p.locked if p else False))

    def _update_assistant(self, module_status: dict) -> None:
        if module_status.get("project") != "complete":
            self.assistant_lbl.setText(
                "<b>Current Step: Project Setup</b><br>"
                "Please fill and save the Project Setup form to initialize your engineering parameters."
            )
            return

        if module_status.get("traffic") != "complete":
            self.assistant_lbl.setText(
                "<b>Current Step: Traffic Survey / MSA</b><br>"
                "Conduct traffic count analysis to compute cumulative design traffic in MSA."
            )
            return

        traffic_msa = 0.0
        if self._project_id is not None and self.db:
            t_row = self.db.latest_traffic_analysis(self._project_id)
            if t_row and t_row.design_msa:
                traffic_msa = t_row.design_msa

        if module_status.get("subgrade") != "complete":
            self.assistant_lbl.setText(
                f"<b>Traffic Analysis Completed (Design Traffic: {traffic_msa:.2f} MSA).</b><br>"
                "<b>Recommended Next Step:</b> Perform Subgrade / CBR evaluation to determine resilient modulus."
            )
            return

        if module_status.get("structural") != "complete":
            self.assistant_lbl.setText(
                "<b>Subgrade Evaluation Completed.</b><br>"
                "<b>Recommended Next Step:</b> Generate pavement structural design compositions."
            )
            return

        if module_status.get("stabilized") != "complete":
            self.assistant_lbl.setText(
                "<b>Structural Design Options Generated.</b><br>"
                "<b>Recommended Next Step:</b> Perform CTB/CTS Alternative Selection for comparison."
            )
            return

        if module_status.get("iitpave_status") != "complete":
            self.assistant_lbl.setText(
                "<b>Alternative Selection Completed.</b><br>"
                "<b>Recommended Next Step:</b> Perform IITPAVE Verification on the selected layer compositions."
            )
            return

        if module_status.get("mix_design") != "complete":
            self.assistant_lbl.setText(
                "<b>IITPAVE Verification Completed.</b><br>"
                "<b>Recommended Next Step:</b> Conduct Marshall Bituminous Mix Design (gradation and binder optimization)."
            )
            return

        if module_status.get("material_qty") != "complete":
            self.assistant_lbl.setText(
                "<b>Bituminous Mix Design Completed.</b><br>"
                "<b>Recommended Next Step:</b> Calculate quantities and cost analysis in BOQ."
            )
            return

        if module_status.get("engineering_review") != "complete":
            self.assistant_lbl.setText(
                "<b>BOQ Calculations Completed.</b><br>"
                "<b>Recommended Next Step:</b> Conduct final Engineering Review checklists and sign-offs."
            )
            return

        if module_status.get("submission") != "complete":
            self.assistant_lbl.setText(
                "<b>Engineering Review Approved.</b><br>"
                "<b>Recommended Next Step:</b> Lock final project design and export submission ZIP delivery package."
            )
            return

        self.assistant_lbl.setText("<b>Project Submitted!</b><br>All workflow stages completed, verified, locked, and packaged.")
