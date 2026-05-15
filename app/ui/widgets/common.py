"""Reusable widget helpers."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class PageHeader(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self.setMinimumHeight(72)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)

        # Optional Back button (hidden unless enable_back() called)
        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("BackBtn")
        self.back_btn.setVisible(False)
        self.back_btn.setFixedWidth(80)
        layout.addWidget(self.back_btn)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        text_box.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            text_box.addWidget(s)
        layout.addLayout(text_box, stretch=1)
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(8)
        layout.addLayout(self.actions_layout)

    def add_action(self, btn: QPushButton) -> None:
        self.actions_layout.addWidget(btn)

    def enable_back(self, handler) -> None:
        """Show the back arrow and wire it to handler()."""
        self.back_btn.setVisible(True)
        self.back_btn.clicked.connect(handler)


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("class", "Card")
        self.setFrameShape(QFrame.StyledPanel)


def make_table(headers: list[str], rows: int = 0) -> QTableWidget:
    t = QTableWidget(rows, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setDefaultSectionSize(26)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    return t


def styled_button(text: str, kind: str = "primary") -> QPushButton:
    b = QPushButton(text)
    if kind == "secondary":
        b.setProperty("class", "Secondary")
    elif kind == "danger":
        b.setProperty("class", "Danger")
    return b
