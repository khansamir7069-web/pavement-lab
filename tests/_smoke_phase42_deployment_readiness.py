"""Phase-42 smoke - local deployment/runtime readiness foundation."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase42_deployment_readiness_"))
_db_path = _tmp / "phase42.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from app.core import (  # noqa: E402
    DEFAULT_FIXTURE_MANIFEST,
    DEPLOYMENT_MANIFEST_FORMAT,
    DEPLOYMENT_SEVERITY_ERROR,
    FIXTURE_STATUS_VERIFIED,
    build_deployment_manifest,
    startup_deployment_diagnostics,
    validate_runtime_environment,
    write_deployment_manifest,
)
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    CombinedReportContext,
    build_combined_report,
    build_report_export_bundle,
    run_iitpave_schema_diagnostics_workflow,
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


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True).lower()


def main() -> int:
    print("=== 1) Runtime directory validation reports missing paths safely ===")
    app_dir = _tmp / "app"
    app_dir.mkdir()
    runtime_root = _tmp / "runtime_missing"
    missing_paths = {
        "reports": runtime_root / "reports",
        "exports": runtime_root / "exports",
        "logs": runtime_root / "logs",
        "diagnostics": runtime_root / "diagnostics",
        "temp": runtime_root / "tmp",
    }
    missing = validate_runtime_environment(
        app_dir=app_dir,
        user_data_dir=runtime_root,
        runtime_paths=missing_paths,
        create_missing=False,
    )
    assert missing.ok is False
    assert any(issue.severity == DEPLOYMENT_SEVERITY_ERROR for issue in missing.issues)
    assert all(not check.exists for check in missing.runtime_paths)
    print("  [PASS] missing runtime paths produce structured non-crashing diagnostics")

    print("\n=== 2) Missing directories can be created and validated as writable ===")
    created = validate_runtime_environment(
        app_dir=app_dir,
        user_data_dir=runtime_root,
        runtime_paths=missing_paths,
        create_missing=True,
    )
    assert created.ok is True
    assert all(check.exists and check.is_directory and check.writable for check in created.runtime_paths)
    assert any(check.created for check in created.runtime_paths)
    print("  [PASS] reports, exports, logs, diagnostics, and temp paths validate writable")

    print("\n=== 3) Deployment metadata manifests generate safely ===")
    manifest = build_deployment_manifest(
        diagnostics=created,
        optional_metadata={"channel": "local-commercial-prep"},
        build_id="phase42-local",
    )
    manifest_path = write_deployment_manifest(_tmp / "deployment_manifest.json", manifest)
    manifest_payload = _read_json(manifest_path)
    assert manifest_payload["format"] == DEPLOYMENT_MANIFEST_FORMAT
    assert manifest_payload["build_id"] == "phase42-local"
    assert manifest_payload["deployment_model"] == "local_only"
    assert manifest_payload["online_activation_enabled"] is False
    assert manifest_payload["encrypted_licensing_enabled"] is False
    assert manifest_payload["optional_metadata"]["channel"] == "local-commercial-prep"
    fallback_manifest = build_deployment_manifest(diagnostics=created)
    fallback_payload = fallback_manifest.as_dict()
    assert fallback_payload["build_id"].startswith("local-")
    assert fallback_payload["optional_metadata"] == {}
    print("  [PASS] deployment manifest exposes build/version/runtime metadata safely")

    print("\n=== 4) Startup diagnostics remain backward compatible and non-fatal ===")
    startup = startup_deployment_diagnostics()
    assert startup.app_dir
    assert startup.user_data_dir
    assert isinstance(startup.as_dict(), dict)
    startup_text = _safe_text(startup.as_dict())
    assert "online_activation" not in startup_text
    assert "license_key" not in startup_text
    print("  [PASS] startup diagnostics return structured metadata without blocking launch")

    print("\n=== 5) Existing report/export workflows still function ===")
    db = Database(_db_path)
    project = db.create_project(
        work_name="Phase 42 Deployment Report",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )
    history = _persist_history(db, project.id)
    report = _tmp / "phase42_combined_report.docx"
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
    assert included == ["IITPAVE Schema Diagnostics History"]
    bundle = build_report_export_bundle(
        _tmp / "phase42_bundle",
        db,
        project.id,
        report_paths=(report,),
    )
    assert bundle.manifest_path.is_file()
    bundle_payload = _read_json(bundle.manifest_path)
    assert bundle_payload["engineering_calculations_allowed"] is False
    combined_text = _safe_text({"deployment": manifest_payload, "bundle": bundle_payload})
    assert "fatigue_life" not in combined_text
    assert "rutting_life" not in combined_text
    assert "irc_compliance" not in combined_text
    assert "point_results" not in combined_text
    print("  [PASS] reporting and deliverable bundle workflows remain compatible")

    print("\nPHASE 42 DEPLOYMENT READINESS SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
