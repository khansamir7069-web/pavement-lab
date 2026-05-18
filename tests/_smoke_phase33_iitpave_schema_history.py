"""Phase-33 smoke - persisted IITPAVE schema diagnostics history."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase33_iitpave_schema_history_"))
_db_path = _tmp / "phase33.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from app.core import DEFAULT_FIXTURE_MANIFEST, FIXTURE_STATUS_VERIFIED  # noqa: E402
from app.db.project_exchange import export_project, import_project  # noqa: E402
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN,
    IITPaveSchemaReportContext,
    run_iitpave_schema_diagnostics_workflow,
)

import app.db.repository as _repo  # noqa: E402


_messages: list[tuple[str, str, str]] = []
QMessageBox.information = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("info", title, message)) or 0
)
QMessageBox.warning = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("warning", title, message)) or 0
)
QMessageBox.critical = staticmethod(
    lambda _parent, title, message, *a, **k: _messages.append(("critical", title, message)) or 0
)


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


def _payload_text(row) -> str:
    return json.dumps(json.loads(row.summary_json), sort_keys=True).lower()


def main() -> int:
    fixture_dir = _fixture_folder()
    db = Database(_db_path)
    project = db.create_project(
        work_name="Phase 33 Schema History",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )

    print("=== 1) Workflow output persists as project history ===")
    report_path = _tmp / "schema_history.docx"
    result = run_iitpave_schema_diagnostics_workflow(
        fixture_dir,
        report_path=report_path,
        context=IITPaveSchemaReportContext(project_title=project.work_name),
    )
    assert result.status == IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN
    row = db.save_iitpave_schema_diagnostics(project_id=project.id, result=result)
    assert row.project_id == project.id
    assert row.fixture_dir == str(fixture_dir)
    assert row.report_path == str(report_path)
    assert row.workflow_status == IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN
    assert row.manifest_status == result.manifest.status
    assert row.parser_audit_ready is True
    assert row.engineering_calculations_allowed is False
    assert row.total_fixture_count == 1
    assert row.verified_fixture_count == 1
    assert row.mapped_schema_count == 1
    assert row.blocked_schema_count == 0
    assert "Engineering calculations remain blocked" in row.operator_message
    print("  [PASS] audit-only workflow summary is persisted")

    print("\n=== 2) Latest/list helpers expose persisted summaries safely ===")
    latest = db.latest_iitpave_schema_diagnostics(project.id)
    history = db.list_iitpave_schema_diagnostics(project.id)
    assert latest is not None
    assert latest.id == row.id
    assert [item.id for item in history] == [row.id]
    serialized = _payload_text(latest)
    assert '"engineering_calculations_allowed": false' in serialized
    assert "report_summary" in serialized
    assert "fixture_dir" in serialized
    assert "fatigue" not in serialized
    assert "rutting" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    print("  [PASS] persisted serialization remains audit-only")

    print("\n=== 3) Project exchange preserves schema diagnostics history ===")
    exported = export_project(db, project.id)
    records = exported["records"]["iitpave_schema_diagnostics"]
    assert len(records) == 1
    assert records[0]["workflow_status"] == IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN
    assert records[0]["engineering_calculations_allowed"] is False
    imported = import_project(db, exported)
    imported_row = db.latest_iitpave_schema_diagnostics(imported.project_id)
    assert imported_row is not None
    assert imported_row.fixture_dir == str(fixture_dir)
    assert imported_row.manifest_status == row.manifest_status
    assert imported_row.engineering_calculations_allowed is False
    print("  [PASS] export/import carries history without calculation fields")

    print("\n=== 4) UI workflow records history when a project is active ===")
    _repo._singleton = db
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    ui_project = w.db.create_project(work_name="Phase 33 UI History", mix_type="DBM-II")
    w._current_project_id = ui_project.id
    ui_report = _tmp / "ui_schema_history.docx"
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(fixture_dir))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(ui_report), "Word"))
    w.btn_iitpave_schema.click()
    ui_row = w.db.latest_iitpave_schema_diagnostics(ui_project.id)
    assert ui_report.is_file()
    assert ui_row is not None
    assert ui_row.report_path == str(ui_report)
    assert ui_row.engineering_calculations_allowed is False
    assert "History #" in w.statusBar().currentMessage()
    assert any("IITPAVE schema diagnostics" in item[1] for item in _messages)
    w.close()
    app.processEvents()
    print("  [PASS] operator workflow persists project-scoped diagnostics history")

    print("\nPHASE 33 IITPAVE SCHEMA HISTORY SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
