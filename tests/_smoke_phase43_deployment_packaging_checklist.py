"""Phase-43 smoke - local deployment packaging checklist and review UI."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase43_deployment_packaging_checklist_"))
_db_path = _tmp / "phase43.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QTextEdit  # noqa: E402

from app.core import (  # noqa: E402
    DEFAULT_FIXTURE_MANIFEST,
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    DEPLOYMENT_CHECK_WARN,
    FIXTURE_STATUS_VERIFIED,
    build_deployment_packaging_checklist,
    format_deployment_checklist_item_text,
    startup_deployment_diagnostics,
    validate_runtime_environment,
)
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    CombinedReportContext,
    build_combined_report,
    build_report_export_bundle,
    run_iitpave_schema_diagnostics_workflow,
)

import app.db.repository as _repo  # noqa: E402


_dialogs: list[QDialog] = []
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


def _persist_history(db: Database, project_id: int):
    result = run_iitpave_schema_diagnostics_workflow(
        _fixture_folder("fixture"),
        report_path=_tmp / "schema_diagnostics.docx",
    )
    return db.save_iitpave_schema_diagnostics(project_id=project_id, result=result)


def _runtime_paths(root: Path) -> dict[str, Path]:
    return {
        "reports": root / "reports",
        "exports": root / "exports",
        "logs": root / "logs",
        "diagnostics": root / "diagnostics",
        "temp": root / "tmp",
    }


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    app_dir = _tmp / "app"
    app_dir.mkdir()

    print("=== 1) Packaging checklist builds safely ===")
    ready_root = _tmp / "runtime_ready"
    ready_diagnostics = validate_runtime_environment(
        app_dir=app_dir,
        user_data_dir=ready_root,
        runtime_paths=_runtime_paths(ready_root),
        create_missing=True,
    )
    ready_checklist = build_deployment_packaging_checklist(
        diagnostics=ready_diagnostics,
        include_iitpave_discovery=False,
    )
    assert ready_checklist.status == DEPLOYMENT_CHECK_PASS
    assert all(item.status == DEPLOYMENT_CHECK_PASS for item in ready_checklist.items)
    assert any(item.key == "report_export_readiness" for item in ready_checklist.items)
    print("  [PASS] ready runtime directories produce an all-PASS checklist")

    print("\n=== 2) PASS/WARN/FAIL statuses render safely ===")
    missing_root = _tmp / "runtime_missing"
    missing_diagnostics = validate_runtime_environment(
        app_dir=app_dir,
        user_data_dir=missing_root,
        runtime_paths=_runtime_paths(missing_root),
        create_missing=False,
    )
    mixed_checklist = build_deployment_packaging_checklist(
        diagnostics=missing_diagnostics,
        include_iitpave_discovery=True,
        iitpave_env={},
        app_dir=app_dir,
    )
    statuses = {item.status for item in mixed_checklist.items}
    assert DEPLOYMENT_CHECK_PASS in statuses
    assert DEPLOYMENT_CHECK_WARN in statuses
    assert DEPLOYMENT_CHECK_FAIL in statuses
    assert mixed_checklist.status == DEPLOYMENT_CHECK_FAIL
    rendered = "\n".join(format_deployment_checklist_item_text(item)
                         for item in mixed_checklist.items)
    assert "Status: PASS" in rendered
    assert "Status: WARN" in rendered
    assert "Status: FAIL" in rendered
    assert "execution remains blocked" in rendered
    print("  [PASS] operator-readable checklist text includes PASS/WARN/FAIL")

    print("\n=== 3) Missing optional metadata is handled safely ===")
    fallback_checklist = build_deployment_packaging_checklist(
        diagnostics=ready_diagnostics,
        optional_metadata=None,
        build_id="",
        include_iitpave_discovery=False,
    )
    fallback_payload = fallback_checklist.as_dict()
    assert fallback_payload["manifest"]["build_id"].startswith("local-")
    assert fallback_payload["manifest"]["optional_metadata"] == {}
    assert isinstance(fallback_payload["operator_summary"], list)
    print("  [PASS] absent optional metadata falls back to readable local metadata")

    print("\n=== 4) Read-only diagnostics view loads without breaking startup ===")
    _repo._singleton = Database(_db_path)
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    startup = startup_deployment_diagnostics()
    assert isinstance(startup.as_dict(), dict)
    w = MainWindow()
    assert w.btn_deployment_diagnostics is not None
    w.btn_deployment_diagnostics.click()
    assert _dialogs
    dialog = _dialogs[-1]
    selector = dialog.findChild(QListWidget)
    detail = dialog.findChild(QTextEdit)
    assert selector is not None
    assert selector.count() >= 1
    assert detail is not None
    assert detail.isReadOnly()
    assert "Status:" in detail.toPlainText()
    assert "Deployment diagnostics loaded:" in w.statusBar().currentMessage()
    w.close()
    app.processEvents()
    print("  [PASS] deployment diagnostics dialog is read-only and non-fatal")

    print("\n=== 5) Existing report/export/deployment workflows remain compatible ===")
    db = Database(_db_path)
    project = db.create_project(
        work_name="Phase 43 Deployment Checklist",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )
    history = _persist_history(db, project.id)
    report = _tmp / "phase43_combined_report.docx"
    _out, included = build_combined_report(
        report,
        db,
        project.id,
        CombinedReportContext(
            project_title=project.work_name,
            work_name=project.work_name,
            agency=project.agency or "",
            submitted_by=project.submitted_by or "",
            mix_type_key=project.mix_type or "",
        ),
        schema_history_selection_ids=(history.id,),
    )
    assert report.is_file()
    assert "IITPAVE Schema Diagnostics History" in included
    bundle = build_report_export_bundle(
        _tmp / "phase43_bundle",
        db,
        project.id,
        report_paths=(report,),
    )
    assert bundle.manifest_path.is_file()
    combined_text = _safe_text({
        "checklist": ready_checklist.as_dict(),
        "bundle": json.loads(bundle.manifest_path.read_text(encoding="utf-8")),
    })
    assert "fatigue_life" not in combined_text
    assert "rutting_life" not in combined_text
    assert "irc_compliance" not in combined_text
    assert "point_results" not in combined_text
    assert "online_activation_enabled" in combined_text
    assert "encrypted_licensing_enabled" in combined_text
    print("  [PASS] report/export and deployment readiness workflows still function")

    print("\nPHASE 43 DEPLOYMENT PACKAGING CHECKLIST SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
