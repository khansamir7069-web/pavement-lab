"""Phase-20 smoke - project export/import foundation.

Pure-Python, no UI. Verifies versioned project export payloads, safe
non-overwriting import, config/profile metadata preservation, fallback
warnings, and malformed-payload rejection.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app import __version__
from app.core import (
    ConditionSurveyInput,
    DistressRecord,
    PROFILE_CONSULTANCY,
    PROFILE_DEFAULT,
    TrafficInput,
    compute_condition_survey,
    compute_traffic_analysis,
)
from app.db.project_exchange import (
    PROJECT_EXPORT_FORMAT,
    PROJECT_EXPORT_FORMAT_VERSION,
    ProjectImportError,
    export_project,
    import_project,
    read_project_export,
    validate_project_export_payload,
    write_project_export,
)
from app.db.repository import Database


_tmp = Path(tempfile.mkdtemp())


def _seed_project(db: Database):
    proj = db.create_project(
        work_name="Phase 20 Export Source",
        agency="State PWD",
        submitted_by="QA Engineer",
        mix_type="DBM-II",
        binder_grade="VG-30",
        binder_properties_json=json.dumps({"penetration": 65}),
    )
    db.set_module_status(proj.id, "condition", "complete")
    db.set_module_status(proj.id, "traffic", "complete")
    db.attach_project_config(proj.id, profile_key=PROFILE_CONSULTANCY)

    condition = compute_condition_survey(ConditionSurveyInput(
        work_name=proj.work_name,
        surveyed_by="QA",
        records=(
            DistressRecord("cracking", "medium", length_m=90.0),
            DistressRecord("potholes", "low", count=2),
        ),
    ))
    db.save_condition_survey(project_id=proj.id, result=condition)

    traffic = compute_traffic_analysis(TrafficInput(
        initial_cvpd=2200.0,
        growth_rate_pct=6.0,
        design_life_years=15,
        terrain="Plain",
        lane_config="Two-lane carriageway",
    ))
    db.save_traffic_analysis(project_id=proj.id, result=traffic)
    return proj


def main() -> int:
    db = Database(_tmp / "phase20.db")

    print("=== 1) Export versioned project payload ===")
    source = _seed_project(db)
    payload = export_project(db, source.id)
    assert payload["format"] == PROJECT_EXPORT_FORMAT
    assert payload["format_version"] == PROJECT_EXPORT_FORMAT_VERSION
    assert payload["application"]["version"] == __version__
    assert payload["project"]["source_id"] == source.id
    assert payload["project"]["work_name"] == source.work_name
    assert payload["project"]["agency"] == "State PWD"
    assert payload["project"]["config"]["profile"] == PROFILE_CONSULTANCY
    assert payload["project"]["config_resolved"]["profile"] == PROFILE_CONSULTANCY
    assert payload["project"]["modules_json"]
    assert len(payload["records"]["condition_surveys"]) == 1
    assert len(payload["records"]["traffic_analyses"]) == 1
    validation = validate_project_export_payload(payload)
    assert validation.ok
    assert payload["validation"]["ok"] is True
    print("  [PASS] payload has format/app/project/config/module metadata")

    print("\n=== 2) File round-trip utility ===")
    export_path = write_project_export(payload, _tmp / "phase20_project_export.json")
    loaded_payload = read_project_export(export_path)
    assert loaded_payload["format"] == PROJECT_EXPORT_FORMAT
    assert loaded_payload["project"]["work_name"] == source.work_name
    print(f"  [PASS] wrote/read {export_path.name}")

    print("\n=== 3) Import creates a new project without overwriting ===")
    result = import_project(db, loaded_payload)
    assert result.project_id != source.id
    assert not any(i.severity == "error" for i in result.issues)
    imported = db.get_project(result.project_id)
    original = db.get_project(source.id)
    assert imported is not None and original is not None
    assert imported.work_name == source.work_name
    assert original.work_name == "Phase 20 Export Source"
    assert imported.mix_type == "DBM-II"
    assert imported.binder_grade == "VG-30"
    assert json.loads(imported.binder_properties_json)["penetration"] == 65
    assert db.get_module_status(imported.id) == {
        "condition": "complete",
        "traffic": "complete",
    }
    assert db.load_project_config(imported.id).profile.key == PROFILE_CONSULTANCY
    assert db.latest_condition_survey(imported.id) is not None
    assert db.latest_traffic_analysis(imported.id) is not None
    print(f"  [PASS] imported project id={imported.id}; source id={source.id} untouched")

    print("\n=== 4) Missing optional metadata imports safely ===")
    minimal = {
        "format": PROJECT_EXPORT_FORMAT,
        "project": {"work_name": "Minimal Imported Project"},
    }
    minimal_validation = validate_project_export_payload(minimal)
    assert minimal_validation.ok
    assert minimal_validation.has_warnings
    minimal_result = import_project(db, minimal)
    minimal_project = db.get_project(minimal_result.project_id)
    assert minimal_project is not None
    assert minimal_project.work_name == "Minimal Imported Project"
    assert db.load_project_config(minimal_project.id).profile.key == PROFILE_DEFAULT
    print("  [PASS] missing optional records/config/version handled with warning")

    print("\n=== 5) Unknown config profile falls back with traceable warning ===")
    unknown_config = {
        "format": PROJECT_EXPORT_FORMAT,
        "format_version": PROJECT_EXPORT_FORMAT_VERSION,
        "project": {
            "work_name": "Unknown Profile Import",
            "config": {"profile": "field-office"},
        },
    }
    unknown_result = import_project(db, unknown_config)
    assert any("Unsupported application profile" in i.message for i in unknown_result.issues)
    unknown_project = db.get_project(unknown_result.project_id)
    assert unknown_project is not None
    unknown_loaded = db.load_project_config(unknown_project.id)
    assert unknown_loaded.profile.key == PROFILE_DEFAULT
    assert unknown_loaded.metadata.requested_profile == "field-office"
    assert unknown_loaded.metadata.fallback_used is True
    assert unknown_loaded.metadata.validation_issues
    print("  [PASS] unsupported config preserved as requested key with fallback warning")

    print("\n=== 6) Malformed payloads are rejected ===")
    for bad_payload in (
        None,
        {"format": "wrong", "project": {"work_name": "Bad"}},
        {"format": PROJECT_EXPORT_FORMAT, "project": {}},
        {
            "format": PROJECT_EXPORT_FORMAT,
            "project": {"work_name": "Bad Records"},
            "records": {"condition_surveys": {"not": "a-list"}},
        },
    ):
        try:
            import_project(db, bad_payload)  # type: ignore[arg-type]
        except ProjectImportError:
            pass
        else:
            raise AssertionError(f"malformed payload was accepted: {bad_payload!r}")
    print("  [PASS] invalid format / missing name / bad records rejected")

    print("\nPHASE 20 PROJECT EXPORT/IMPORT SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
