"""Phase-21 smoke - project exchange UI wiring.

Verifies the dashboard-level import/export controls call the Phase-20
validated project-exchange foundation without overwriting existing projects.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = Path(tempfile.mkdtemp())
_db_path = _tmp / "phase21.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

QMessageBox.information = staticmethod(lambda *a, **k: 0)
QMessageBox.warning = staticmethod(lambda *a, **k: 0)
QMessageBox.critical = staticmethod(lambda *a, **k: 0)

import app.db.repository as _repo  # noqa: E402
from app.db.project_exchange import read_project_export  # noqa: E402
from app.db.repository import Database  # noqa: E402


def main() -> int:
    _repo._singleton = Database(_db_path)

    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    source = w.db.create_project(
        work_name="Phase 21 Exchange UI",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
        binder_grade="VG-30",
    )
    w.db.set_module_status(source.id, "traffic", "complete")
    w.dashboard.refresh()

    print("=== 1) Dashboard exposes project exchange controls ===")
    assert w.dashboard.btn_import_project is not None
    assert w.dashboard.table.columnCount() == 7
    export_btn = w.dashboard.table.cellWidget(0, 5)
    assert export_btn is not None
    print("  [PASS] import action and per-row export action are present")

    print("\n=== 2) Per-row export writes a validated JSON payload ===")
    export_path = _tmp / "phase21_project_export.json"
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(export_path), "JSON")
    )
    export_btn.click()
    assert export_path.exists()
    payload = read_project_export(export_path)
    assert payload["project"]["work_name"] == source.work_name
    assert payload["project"]["binder_grade"] == "VG-30"
    assert payload["records"]["traffic_analyses"] == []
    print(f"  [PASS] exported {export_path.name}")

    print("\n=== 3) Dashboard import creates a new current project ===")
    before = {p.id for p in w.db.list_projects()}
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **k: (str(export_path), "JSON")
    )
    w.dashboard.btn_import_project.click()
    projects = w.db.list_projects()
    after = {p.id for p in projects}
    new_ids = after - before
    assert len(new_ids) == 1
    imported_id = new_ids.pop()
    imported = w.db.get_project(imported_id)
    assert imported is not None
    assert imported.id != source.id
    assert imported.work_name == source.work_name
    assert imported.binder_grade == "VG-30"
    assert w._current_project_id == imported.id
    assert w.db.get_module_status(imported.id) == {"traffic": "complete"}
    assert w.stack.currentWidget() is w.hub
    print(f"  [PASS] imported project id={imported.id}; source id={source.id} untouched")

    w.close()
    app.processEvents()
    print("\nPHASE 21 PROJECT EXCHANGE UI SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
