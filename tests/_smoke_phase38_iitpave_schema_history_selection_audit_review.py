"""Phase-38 smoke - operator review of report-time schema-history selection audits."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase38_iitpave_schema_history_selection_audit_review_"))
_db_path = _tmp / "phase38.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QMessageBox, QTextEdit  # noqa: E402

from app.core import DEFAULT_FIXTURE_MANIFEST, FIXTURE_STATUS_VERIFIED  # noqa: E402
from app.db.project_exchange import export_project, import_project  # noqa: E402
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    CombinedReportContext,
    IITPAVE_SCHEMA_HISTORY_SELECTION_AUDIT_REVIEW_STATUS_AVAILABLE,
    IITPAVE_SCHEMA_HISTORY_SELECTION_AUDIT_REVIEW_STATUS_EMPTY,
    build_combined_report,
    build_iitpave_schema_history_selection_audit_review,
    format_iitpave_schema_history_selection_audit_item_text,
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


def _fixture_folder(name: str) -> Path:
    folder = _tmp / name
    folder.mkdir(exist_ok=True)
    sample = _write_fixture(folder, f"{name}.out", [
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


def _persist_history_pair(db: Database, project_id: int) -> tuple:
    first = run_iitpave_schema_diagnostics_workflow(
        _fixture_folder("first_fixture"),
        report_path=_tmp / "first_schema_diagnostics.docx",
    )
    second = run_iitpave_schema_diagnostics_workflow(
        _fixture_folder("second_fixture"),
        report_path=_tmp / "second_schema_diagnostics.docx",
    )
    row1 = db.save_iitpave_schema_diagnostics(project_id=project_id, result=first)
    row2 = db.save_iitpave_schema_diagnostics(project_id=project_id, result=second)
    return row1, row2


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True).lower()


def main() -> int:
    db = Database(_db_path)
    project = db.create_project(
        work_name="Phase 38 Selection Audit Review",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )
    empty_project = db.create_project(work_name="Phase 38 Empty Project", mix_type="DBM-II")
    row1, row2 = _persist_history_pair(db, project.id)

    print("=== 1) Empty projects expose no selection-audit records safely ===")
    empty_review = build_iitpave_schema_history_selection_audit_review(
        empty_project.id,
        db.list_iitpave_schema_history_selection_audits(empty_project.id),
    )
    assert empty_review.status == IITPAVE_SCHEMA_HISTORY_SELECTION_AUDIT_REVIEW_STATUS_EMPTY
    assert empty_review.item_count == 0
    assert "No report-time IITPAVE schema history selection audit records" in (
        "\n".join(empty_review.operator_summary)
    )
    print("  [PASS] empty audit review is safe and operator-readable")

    print("\n=== 2) Report/export behavior still records a readable audit decision ===")
    selected_doc = _tmp / "phase38_selected_schema_history.docx"
    _out, included = build_combined_report(
        selected_doc,
        db,
        project.id,
        CombinedReportContext(
            project_title=project.work_name,
            work_name=project.work_name,
            agency=project.agency or "",
            submitted_by=project.submitted_by or "",
            mix_type_key=project.mix_type or "",
        ),
        schema_history_selection_ids=(999999, row1.id),
    )
    assert included == ["IITPAVE Schema Diagnostics History"]
    rows = db.list_iitpave_schema_history_selection_audits(project.id)
    review = build_iitpave_schema_history_selection_audit_review(project.id, rows)
    assert review.status == IITPAVE_SCHEMA_HISTORY_SELECTION_AUDIT_REVIEW_STATUS_AVAILABLE
    assert review.item_count == 1
    item = review.latest_item
    assert item is not None
    assert item.available_history_ids == (row2.id, row1.id)
    assert item.selected_history_ids == (row1.id,)
    assert item.skipped_unknown_history_ids == (999999,)
    assert item.engineering_calculations_allowed is False
    item_text = format_iitpave_schema_history_selection_audit_item_text(item)
    assert "Selected schema history IDs" in item_text
    assert "Available candidate history IDs" in item_text
    assert "Decision status" in item_text
    assert "Report path" in item_text
    assert "Warning:" in item_text
    assert "not remapped" in item_text
    serialized = _safe_text(review.as_dict())
    assert "fatigue_life" not in serialized
    assert "rutting_life" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    print("  [PASS] persisted audit records can be listed and read by project")

    print("\n=== 3) Imported preserved audit IDs are visible without remapping ===")
    exported = export_project(db, project.id)
    imported = import_project(db, exported)
    imported_review = build_iitpave_schema_history_selection_audit_review(
        imported.project_id,
        db.list_iitpave_schema_history_selection_audits(imported.project_id),
    )
    imported_history_ids = tuple(
        row.id for row in db.list_iitpave_schema_diagnostics(imported.project_id)
    )
    imported_item = imported_review.latest_item
    assert imported_item is not None
    assert imported_item.selected_history_ids == (row1.id,)
    assert imported_item.selected_history_ids != imported_history_ids[:1]
    imported_text = format_iitpave_schema_history_selection_audit_item_text(imported_item)
    assert "Historical IDs are shown exactly as recorded" in imported_text
    assert "not remapped" in imported_text
    print("  [PASS] imported audit provenance is displayed as preserved history IDs")

    print("\n=== 4) UI exposes read-only active-project report audit review ===")
    _repo._singleton = db
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    assert w.btn_iitpave_schema_report_audit is not None
    w.btn_iitpave_schema_report_audit.click()
    assert any(item[0] == "warning" and "report audit" in item[1] for item in _messages)
    w._current_project_id = empty_project.id
    w.btn_iitpave_schema_report_audit.click()
    assert any(item[0] == "info" and "report audit" in item[1] for item in _messages)
    w._current_project_id = project.id
    w.btn_iitpave_schema_report_audit.click()
    assert _dialogs
    dialog = _dialogs[-1]
    selector = dialog.findChild(QListWidget)
    detail = dialog.findChild(QTextEdit)
    assert selector is not None
    assert selector.count() == 1
    assert detail is not None
    assert "Selected schema history IDs" in detail.toPlainText()
    assert "Engineering calculations remain blocked" in detail.toPlainText()
    assert "IITPAVE schema-history report audit loaded: 1 record(s)." in (
        w.statusBar().currentMessage()
    )
    w.close()
    app.processEvents()
    print("  [PASS] UI dialog lists and displays read-only selection audit records")

    print("\nPHASE 38 IITPAVE SCHEMA HISTORY SELECTION AUDIT REVIEW SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
