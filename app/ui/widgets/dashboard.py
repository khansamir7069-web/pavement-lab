"""Dashboard: project list + new-project button + KPI tiles."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .common import Card, PageHeader, styled_button


class Dashboard(QWidget):
    new_project = Signal()
    open_project = Signal(int)        # project_id
    delete_project = Signal(int)      # project_id

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PageHeader("Dashboard", "Recent projects and lab activity")
        self.btn_new = styled_button("+ New Project")
        self.btn_new.clicked.connect(self.new_project.emit)
        header.add_action(self.btn_new)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(14)

        # KPI tiles
        kpi_row = QHBoxLayout()
        self.kpi_projects = self._make_kpi("Projects", "—")
        self.kpi_clients = self._make_kpi("Clients", "—")
        self.kpi_reports = self._make_kpi("Reports", "—")
        kpi_row.addWidget(self.kpi_projects[0])
        kpi_row.addWidget(self.kpi_clients[0])
        kpi_row.addWidget(self.kpi_reports[0])
        body_layout.addLayout(kpi_row)

        # Project list
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.addWidget(QLabel("<b>Recent Projects</b>"))

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Work Name", "Mix Type", "Modules", "Updated", ""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 90)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self._on_row_open)
        cl.addWidget(self.table)
        body_layout.addWidget(card)
        body_layout.addStretch(1)
        layout.addWidget(body, stretch=1)

    def _make_kpi(self, label: str, value: str) -> tuple[QFrame, QLabel]:
        card = Card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 14, 20, 14)
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet("font-size:24pt; font-weight:bold; color:#1f3a68;")
        lbl_lbl = QLabel(label.upper())
        lbl_lbl.setStyleSheet("color:#6a7180; font-size:9pt; letter-spacing:1.5px;")
        v.addWidget(lbl_val)
        v.addWidget(lbl_lbl)
        return card, lbl_val

    def refresh(self) -> None:
        import json
        projects = self.db.list_projects()
        self.table.setRowCount(len(projects))
        for r, p in enumerate(projects):
            self.table.setItem(r, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(r, 1, QTableWidgetItem(p.work_name or ""))
            self.table.setItem(r, 2, QTableWidgetItem(p.mix_type or "—"))
            # Modules summary
            mods_text = "—"
            try:
                mods = json.loads(p.modules_json) if p.modules_json else {}
                done = [k for k, v in mods.items() if v == "complete"]
                if done:
                    mods_text = ", ".join(done)
            except (json.JSONDecodeError, AttributeError):
                pass
            self.table.setItem(r, 3, QTableWidgetItem(mods_text))
            self.table.setItem(r, 4, QTableWidgetItem(
                p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else ""))
            for c in range(5):
                if self.table.item(r, c):
                    self.table.item(r, c).setTextAlignment(Qt.AlignCenter)
            # Delete button in col 5
            del_btn = QPushButton("Delete")
            del_btn.setProperty("class", "Danger")
            del_btn.setStyleSheet(
                "background:#c04545; color:white; border:none; padding:4px 10px; border-radius:3px;"
            )
            del_btn.clicked.connect(lambda _=False, pid=p.id, name=p.work_name: self._on_delete(pid, name))
            self.table.setCellWidget(r, 5, del_btn)
        self.kpi_projects[1].setText(str(len(projects)))
        self.kpi_clients[1].setText(str(len(self.db.list_clients())))
        n_reports = 0
        for p in projects:
            md = self.db.latest_mix_design(p.id)
            if md:
                n_reports += len(self.db.list_reports(md.id))
        self.kpi_reports[1].setText(str(n_reports))

    def _on_delete(self, project_id: int, name: str) -> None:
        resp = QMessageBox.question(
            self, "Delete project?",
            f"Permanently delete project #{project_id} — \"{name}\"?\n"
            "All mix designs and reports linked to this project will also be removed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.delete_project.emit(project_id)

    def _on_row_open(self, item: QTableWidgetItem) -> None:
        row = item.row()
        pid_item = self.table.item(row, 0)
        if pid_item:
            try:
                pid = int(pid_item.text())
                self.open_project.emit(pid)
            except ValueError:
                pass
