"""Phase-40 smoke - report revision snapshot and review foundation."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase40_report_revision_snapshots_"))
_db_path = _tmp / "phase40.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QMessageBox, QTextEdit  # noqa: E402

from app.core import DEFAULT_FIXTURE_MANIFEST, FIXTURE_STATUS_VERIFIED  # noqa: E402
from app.db.project_exchange import export_project, import_project  # noqa: E402
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    CombinedReportContext,
    REPORT_REVISION_HISTORY_STATUS_AVAILABLE,
    REPORT_REVISION_HISTORY_STATUS_EMPTY,
    build_combined_report,
    build_report_revision_history_review,
    format_report_revision_snapshot_text,
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
        work_name="Phase 40 Revision Snapshots",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )
    empty_project = db.create_project(work_name="Phase 40 Empty Project", mix_type="DBM-II")
    row1, row2 = _persist_history_pair(db, project.id)

    print("=== 1) Empty revision history behaves safely ===")
    empty_review = build_report_revision_history_review(
        empty_project.id,
        db.list_report_revision_snapshots(empty_project.id),
    )
    assert empty_review.status == REPORT_REVISION_HISTORY_STATUS_EMPTY
    assert empty_review.item_count == 0
    assert "No report revision snapshots" in "\n".join(empty_review.operator_summary)
    print("  [PASS] empty revision snapshot review is safe")

    print("\n=== 2) Generated reports persist revision snapshots safely ===")
    report1 = _tmp / "phase40_revision_1.docx"
    _out, included = build_combined_report(
        report1,
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
    rows = db.list_report_revision_snapshots(project.id)
    review = build_report_revision_history_review(project.id, rows)
    assert review.status == REPORT_REVISION_HISTORY_STATUS_AVAILABLE
    assert review.item_count == 1
    item = review.latest_item
    assert item is not None
    assert item.revision_label == "R001"
    assert item.report_identifier.startswith(f"combined_report:{project.id}:")
    assert len(item.provenance_fingerprint) == 64
    assert item.schema_history_available_ids == (row2.id, row1.id)
    assert item.schema_history_selected_ids == (row1.id,)
    assert item.schema_history_unknown_ids == (999999,)
    assert item.validation_warning_count >= 1
    item_text = format_report_revision_snapshot_text(item)
    assert "Comparison-ready snapshot only" in item_text
    assert "full document diff is not implemented" in item_text
    assert "Imported historical revision IDs are preserved" in item_text
    serialized = _safe_text(review.as_dict())
    assert "provenance_fingerprint" in serialized
    assert "fatigue_life" not in serialized
    assert "rutting_life" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    print("  [PASS] revision snapshot stores fingerprint, warnings, and selection summary")

    print("\n=== 3) Multiple revisions are comparison-ready without diff engine ===")
    report2 = _tmp / "phase40_revision_2.docx"
    build_combined_report(
        report2,
        db,
        project.id,
        CombinedReportContext(
            project_title=project.work_name,
            work_name=project.work_name,
            agency=project.agency or "",
            submitted_by=project.submitted_by or "",
            mix_type_key=project.mix_type or "",
        ),
        schema_history_selection_ids=(row2.id,),
    )
    review2 = build_report_revision_history_review(
        project.id,
        db.list_report_revision_snapshots(project.id),
    )
    assert review2.item_count == 2
    assert review2.latest_item is not None
    assert review2.latest_item.revision_label == "R002"
    labels = tuple(item.revision_label for item in review2.items)
    assert labels == ("R002", "R001")
    fingerprints = {item.provenance_fingerprint for item in review2.items}
    assert len(fingerprints) == 2
    assert all("Comparison-ready snapshot only" in "\n".join(item.comparison_summary)
               for item in review2.items)
    print("  [PASS] revision history lists compact comparison-ready summaries")

    print("\n=== 4) Export/import preserves historical revision provenance ===")
    exported = export_project(db, project.id)
    assert len(exported["records"]["report_revision_snapshots"]) == 2
    imported = import_project(db, exported)
    imported_review = build_report_revision_history_review(
        imported.project_id,
        db.list_report_revision_snapshots(imported.project_id),
    )
    assert imported_review.item_count == 2
    imported_item = imported_review.latest_item
    assert imported_item is not None
    assert imported_item.revision_label == "R002"
    assert imported_item.schema_history_selected_ids == (row2.id,)
    imported_history_ids = tuple(
        row.id for row in db.list_iitpave_schema_diagnostics(imported.project_id)
    )
    assert imported_item.schema_history_selected_ids != imported_history_ids[:1]
    assert "no remapping is performed" in format_report_revision_snapshot_text(imported_item)
    print("  [PASS] imported revision snapshots preserve historical selected IDs")

    print("\n=== 5) UI exposes read-only report revision history ===")
    _repo._singleton = db
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    assert w.btn_report_revisions is not None
    w.btn_report_revisions.click()
    assert any(item[0] == "warning" and "Report revisions" in item[1] for item in _messages)
    w._current_project_id = empty_project.id
    w.btn_report_revisions.click()
    assert any(item[0] == "info" and "Report revisions" in item[1] for item in _messages)
    w._current_project_id = project.id
    w.btn_report_revisions.click()
    assert _dialogs
    dialog = _dialogs[-1]
    selector = dialog.findChild(QListWidget)
    detail = dialog.findChild(QTextEdit)
    assert selector is not None
    assert selector.count() == 2
    assert detail is not None
    assert "Comparison-ready snapshot only" in detail.toPlainText()
    assert "Engineering calculations remain blocked" in detail.toPlainText()
    assert "Report revision snapshots loaded: 2 record(s)." in (
        w.statusBar().currentMessage()
    )
    w.close()
    app.processEvents()
    print("  [PASS] UI dialog lists and displays read-only revision snapshots")

    print("\nPHASE 40 REPORT REVISION SNAPSHOTS SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
