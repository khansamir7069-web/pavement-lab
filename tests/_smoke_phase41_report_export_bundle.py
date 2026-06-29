"""Phase-41 smoke - consultancy report export bundle packaging."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase41_report_export_bundle_"))
_db_path = _tmp / "phase41.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from app.core import DEFAULT_FIXTURE_MANIFEST, FIXTURE_STATUS_VERIFIED  # noqa: E402
from app.db.project_exchange import export_project, import_project  # noqa: E402
from app.db.repository import Database  # noqa: E402
from app.reports import (  # noqa: E402
    CombinedReportContext,
    REPORT_EXPORT_BUNDLE_FORMAT,
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


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True).lower()


def main() -> int:
    db = Database(_db_path)
    project = db.create_project(
        work_name="Phase 41 Export Bundle",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
    )
    empty_project = db.create_project(work_name="Phase 41 Empty Bundle", mix_type="DBM-II")
    row1, _row2 = _persist_history_pair(db, project.id)

    print("=== 1) Export bundle generates safely with report artifacts ===")
    report = _tmp / "phase41_combined_report.docx"
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
        schema_history_selection_ids=(999999, row1.id),
    )
    assert "IITPAVE Schema Diagnostics History" in included
    missing_report = _tmp / "missing_optional_report.docx"
    bundle = build_report_export_bundle(
        _tmp / "bundle_populated",
        db,
        project.id,
        report_paths=(report, missing_report),
    )
    assert bundle.manifest_path.is_file()
    assert bundle.manifest.bundle_id.startswith(f"ROADX-P{project.id}-") or bundle.manifest.bundle_id.startswith(f"SAMPAVE-P{project.id}-")
    assert bundle.manifest.present_artifact_count >= 6
    manifest = _read_json(bundle.manifest_path)
    assert manifest["format"] == REPORT_EXPORT_BUNDLE_FORMAT
    assert manifest["engineering_calculations_allowed"] is False
    assert any(a["kind"] == "generated_report" and a["present"] for a in manifest["artifacts"])
    assert any(a["kind"] == "generated_report" and not a["present"] for a in manifest["artifacts"])
    assert any("optional report artifacts were missing" in w.lower() for w in manifest["warnings"])
    assert (bundle.bundle_dir / "reports" / report.name).is_file()
    print("  [PASS] bundle manifest records copied and missing report artifacts")

    print("\n=== 2) Bundle summary manifests render safely ===")
    provenance = _read_json(bundle.bundle_dir / "provenance_summaries.json")
    revisions = _read_json(bundle.bundle_dir / "revision_snapshots.json")
    warnings = _read_json(bundle.bundle_dir / "validation_warnings.json")
    schema_audits = _read_json(bundle.bundle_dir / "schema_history_audits.json")
    metadata = _read_json(bundle.bundle_dir / "export_metadata.json")
    assert provenance["bundle_id"] == bundle.manifest.bundle_id
    assert revisions["item_count"] == 1
    assert warnings["warning_count"] >= 1
    assert schema_audits["item_count"] == 1
    assert metadata["optional_artifact_policy"]
    bundle_text = _safe_text({
        "manifest": manifest,
        "provenance": provenance,
        "revisions": revisions,
        "warnings": warnings,
        "schema_audits": schema_audits,
        "metadata": metadata,
    })
    assert "provenance_fingerprint" in bundle_text
    assert "selection_audit" in bundle_text
    assert "fatigue_life" not in bundle_text
    assert "rutting_life" not in bundle_text
    assert "irc_compliance" not in bundle_text
    assert "point_results" not in bundle_text
    print("  [PASS] provenance, revision, warning, audit, and metadata manifests render")

    print("\n=== 3) Missing optional artifacts and empty metadata are handled safely ===")
    empty_bundle = build_report_export_bundle(
        _tmp / "bundle_empty",
        db,
        empty_project.id,
    )
    empty_manifest = _read_json(empty_bundle.manifest_path)
    empty_revisions = _read_json(empty_bundle.bundle_dir / "revision_snapshots.json")
    empty_audits = _read_json(empty_bundle.bundle_dir / "schema_history_audits.json")
    assert empty_revisions["item_count"] == 0
    assert empty_audits["item_count"] == 0
    assert any("no generated report files" in w.lower() for w in empty_manifest["warnings"])
    assert any("no report revision snapshots" in w.lower() for w in empty_manifest["warnings"])
    assert any("no schema-history selection audit" in w.lower() for w in empty_manifest["warnings"])
    print("  [PASS] empty bundle keeps summary files and warnings instead of failing")

    print("\n=== 4) Existing report generation and project exchange remain compatible ===")
    exported = export_project(db, project.id)
    imported = import_project(db, exported)
    imported_report = _tmp / "phase41_imported_combined_report.docx"
    imported_project = db.get_project(imported.project_id)
    imported_rows = db.list_iitpave_schema_diagnostics(imported.project_id)
    _out, imported_included = build_combined_report(
        imported_report,
        db,
        imported.project_id,
        CombinedReportContext(
            project_title=imported.work_name,
            work_name=imported.work_name,
            agency=imported_project.agency if imported_project else "",
            submitted_by=imported_project.submitted_by if imported_project else "",
            mix_type_key=imported_project.mix_type if imported_project else "",
        ),
        schema_history_selection_ids=(imported_rows[-1].id,),
    )
    assert "IITPAVE Schema Diagnostics History" in imported_included
    imported_bundle = build_report_export_bundle(
        _tmp / "bundle_imported",
        db,
        imported.project_id,
        report_paths=(imported_report,),
    )
    imported_revision_payload = _read_json(imported_bundle.bundle_dir / "revision_snapshots.json")
    assert imported_revision_payload["item_count"] >= 1
    imported_text = _safe_text(imported_revision_payload)
    assert "no remapping is performed" in imported_text
    assert "provenance_fingerprint" in imported_text
    print("  [PASS] imported provenance and revision metadata remain bundle-ready")

    print("\nPHASE 41 REPORT EXPORT BUNDLE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
