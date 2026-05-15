"""Module Hub — grid of clickable module cards for the current project.

Each card is independent; clicking emits ``module_selected(key)``.  The hub
also shows per-module status badges (empty / in-progress / complete) read
from ``Project.modules_json``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .common import Card, PageHeader


MODULES: tuple[tuple[str, str, str], ...] = (
    # (key, title, description)
    ("mix_design",    "Bituminous Mix Design",
        "Marshall mix design (DBM / BC / SDBC / SDAC / BM …)"),
    ("traffic",       "Traffic / ESAL / MSA",
        "IRC:37 — CVPD, VDF, LDF → design MSA & AASHTO ESAL"),
    ("structural",    "Flexible Pavement Structural Design",
        "IRC:37 — traffic, CBR, layer thickness"),
    ("maintenance",   "Maintenance / Rehabilitation",
        "Overlay / BBD · Cold mix · Slurry · Micro surfacing"),
    ("material_qty",  "Material Quantity Calculator",
        "Quantities for a road stretch (area × thickness × density)"),
    ("condition",     "Pavement Condition Survey",
        "Distress recording · PCI score · rehab placeholders (ASTM D6433)"),
    ("specs_admin",   "Specification Database",
        "View / edit mix-type limits, gradations and binder rules"),
    ("reports",       "Reports",
        "Generate Word reports — per module or combined"),
)

STATUS_BADGE = {
    "complete":    ("✓ Complete", "#1d7a3a", "#e0f2e7"),
    "in_progress": ("● In progress", "#a06d00", "#fbf2d3"),
    "empty":       ("Not started", "#6a7180", "#eef0f4"),
}


class ModuleCard(Card):
    """Clickable card with title, description, and status badge."""

    def __init__(self, key: str, title: str, description: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName("ModuleCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(135)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(6)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(
            "font-size:13pt; font-weight:bold; color:#1f3a68;"
        )
        v.addWidget(self.title_lbl)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#6a7180; font-size:9pt;")
        v.addWidget(desc)
        v.addStretch(1)

        # Status badge
        self.badge = QLabel("Not started")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedHeight(22)
        self._set_status("empty")
        v.addWidget(self.badge, 0, Qt.AlignLeft)

    def _set_status(self, status: str) -> None:
        text, fg, bg = STATUS_BADGE.get(status, STATUS_BADGE["empty"])
        self.badge.setText(text)
        self.badge.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"font-size:8pt; font-weight:bold; padding:2px 10px; border-radius:10px;"
        )

    def set_status(self, status: str) -> None:
        self._set_status(status)

    def mousePressEvent(self, ev):                       # noqa: N802
        if ev.button() == Qt.LeftButton:
            self.parent_hub._emit(self.key)
        super().mousePressEvent(ev)


class ModuleHub(QWidget):
    module_selected = Signal(str)   # key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._project_name: str = ""
        self._cards: dict[str, ModuleCard] = {}
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = PageHeader(
            "Project Workspace",
            "Pick a module to work on. Each module is independent — "
            "you don't need to fill all of them."
        )
        lay.addWidget(self.header)

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

        # Cards grid (3 columns)
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (key, title, desc) in enumerate(MODULES):
            card = ModuleCard(key, title, desc)
            card.parent_hub = self
            self._cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        body_lay.addLayout(grid)
        body_lay.addStretch(1)

        lay.addWidget(body, stretch=1)

    def _emit(self, key: str) -> None:
        self.module_selected.emit(key)

    def set_project(self, project_id: int | None, name: str,
                    module_status: dict | None = None) -> None:
        self._project_id = project_id
        self._project_name = name or "(Unnamed Project)"
        if project_id is None:
            self.proj_banner.setText("No project selected.")
        else:
            self.proj_banner.setText(
                f"<b>Project #{project_id}:</b> {self._project_name}"
            )
        module_status = module_status or {}
        for key, card in self._cards.items():
            card.set_status(module_status.get(key, "empty"))
