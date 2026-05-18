"""Phase-34 smoke - operator review of persisted IITPAVE schema history."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase34_iitpave_schema_history_review_"))
_db_path = _tmp / "phase34.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QListWidget,
    QMessageBox,
    QTextEdit,
)

from app.core import DEFAULT_FIXTURE_MANIFEST, FIXTURE_STATUS_VERIFIED  # noqa: E402
from app.db.project_exchange import export_project, import_project  # noqa: E402
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    IITPAVE_SCHEMA_HISTORY_STATUS_AVAILABLE,
    IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN,
    IITPAVE_SCHEMA_WORKFLOW_STATUS_SUMMARY_ONLY,
    IITPaveSchemaReportContext,
    build_iitpave_schema_history_review,
    format_iitpave_schema_history_item_text,
    run_iitpave_schema_diagnostics_workflow,
)

import app.db.repository as _repo  # noqa: E402


_messages: list[tuple[str, str, str]] = []
_dialogs: list[QDialog] = []
QMessageBox.information = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("info", title, message)) or 0
)
QMessageBox.warning = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("warning", title, message)) or 0
)
QMessageBox.critical = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("critical", title, message)) or 0
)
QDialog.exec = lambda self, *a, **k: _dialogs.append(self) or 0


def _write_manifest(folder: Path, fixtures: list[dict]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({"fixtures": fixtures}, indent=2),
        encoding="utf-8",
    )


def _write_fixture(folder: Path, name: str, lines: list[str]) -> Path:
    path = folder / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _fixture_folder() -> Path:
    folder = _tmp / "fixtures"
    folder.mkdir(exist_ok=True)
    sample = _write_fixture(folder, "direct_stress_strain.out", [
        "IITPAVE OUTPUT",
        "Stress and Strain table",
        "Layer Radius Value",
        "1 0.0 12.3",
    ])
    _write_manifest(folder, [{
        "filename": sample.name,
        "verification_status": FIXTURE_STATUS_VERIFIED,
    }])
    return folder


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True).lower()


def main() -> int:
    fixture_dir = _fixture_folder()
    db = Database(_db_path)
    project = db.create_project(work_name="Phase 34 History Review", mix_type="DBM-II")
    other = db.create_project(work_name="Phase 34 Other Project", mix_type="DBM-II")

    print("=== 1) Persisted history can be recalled as typed review data ===")
    written = run_iitpave_schema_diagnostics_workflow(
        fixture_dir,
        report_path=_tmp / "phase34_schema_report.docx",
        context=IITPaveSchemaReportContext(project_title=project.work_name),
    )
    summary_only = run_iitpave_schema_diagnostics_workflow(fixture_dir)
    assert written.status == IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN
    assert summary_only.status == IITPAVE_SCHEMA_WORKFLOW_STATUS_SUMMARY_ONLY
    row1 = db.save_iitpave_schema_diagnostics(project_id=project.id, result=written)
    row2 = db.save_iitpave_schema_diagnostics(project_id=project.id, result=summary_only)
    review = build_iitpave_schema_history_review(
        project.id,
        db.list_iitpave_schema_diagnostics(project.id),
    )
    assert review.status == IITPAVE_SCHEMA_HISTORY_STATUS_AVAILABLE
    assert review.engineering_calculations_allowed is False
    assert review.item_count == 2
    assert review.latest_item is not None
    assert review.latest_item.id == row2.id
    assert db.get_iitpave_schema_diagnostics(project_id=project.id, history_id=row1.id) is not None
    assert db.get_iitpave_schema_diagnostics(project_id=other.id, history_id=row1.id) is None
    print("  [PASS] history review is project-scoped and typed")

    print("\n=== 2) Recalled summaries remain audit-only and operator-readable ===")
    latest_text = format_iitpave_schema_history_item_text(review.latest_item)
    assert "History #" in latest_text
    assert "Workflow status:" in latest_text
    assert "Fixture counts:" in latest_text
    assert "Engineering calculations remain blocked" in latest_text
    serialized = _safe_text(review.as_dict())
    assert '"engineering_calculations_allowed": false' in serialized
    assert "diagnostic_rows" in serialized
    assert "fatigue" not in serialized
    assert "rutting" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    print("  [PASS] review serialization carries no engineering result payload")

    print("\n=== 3) Export/import keeps recalled history reviewable ===")
    exported = export_project(db, project.id)
    imported = import_project(db, exported)
    imported_review = build_iitpave_schema_history_review(
        imported.project_id,
        db.list_iitpave_schema_diagnostics(imported.project_id),
    )
    assert imported_review.item_count == 2
    assert imported_review.engineering_calculations_allowed is False
    assert imported_review.latest_item is not None
    assert imported_review.latest_item.workflow_status == row2.workflow_status
    print("  [PASS] imported history remains available for audit recall")

    print("\n=== 4) UI exposes active-project history review workflow ===")
    _repo._singleton = db
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    assert w.btn_iitpave_schema_history is not None
    w.btn_iitpave_schema_history.click()
    assert any(item[0] == "warning" and "schema history" in item[1] for item in _messages)
    w._current_project_id = project.id
    w.btn_iitpave_schema_history.click()
    assert _dialogs
    dialog = _dialogs[-1]
    selector = dialog.findChild(QListWidget)
    detail = dialog.findChild(QTextEdit)
    assert selector is not None
    assert selector.count() == 2
    assert detail is not None
    assert "Engineering calculations remain blocked" in detail.toPlainText()
    assert "IITPAVE schema diagnostics history loaded: 2 record(s)." in (
        w.statusBar().currentMessage()
    )
    w.close()
    app.processEvents()
    print("  [PASS] UI recall dialog lists and displays persisted schema diagnostics")

    print("\nPHASE 34 IITPAVE SCHEMA HISTORY REVIEW SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
