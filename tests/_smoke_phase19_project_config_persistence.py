"""Phase-19 smoke - project-level config/profile persistence.

Pure-Python, no UI. Uses temporary SQLite files to verify that project
workflow profile metadata is stored as additive JSON, loads safely for
old projects, and falls back through the central Phase-18 config helpers
for unknown or malformed config.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core import (
    CONFIG_SCHEMA_VERSION,
    PROFILE_CONSULTANCY,
    PROFILE_DEFAULT,
    PROFILE_DEMO,
    PROFILE_LAB,
)
from app.db.repository import Database


_tmp = Path(tempfile.mkdtemp())


def _project_columns(db: Database) -> set[str]:
    with db.engine.begin() as conn:
        return {r[1] for r in conn.execute(text("PRAGMA table_info(projects)"))}


def _project_config_json(db: Database, project_id: int) -> dict:
    p = db.get_project(project_id)
    assert p is not None
    assert p.config_json
    return json.loads(p.config_json)


def _create_legacy_db(path: Path) -> None:
    stamp = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                client_id INTEGER,
                work_name VARCHAR(300) NOT NULL,
                work_order_no VARCHAR(100),
                work_order_date VARCHAR(50),
                agency VARCHAR(200),
                submitted_by VARCHAR(200),
                mix_type VARCHAR(20) NOT NULL DEFAULT '',
                status VARCHAR(20),
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        con.execute(
            """
            INSERT INTO projects
                (id, work_name, mix_type, status, created_at, updated_at)
            VALUES
                (1, 'Legacy project without config metadata', '', 'draft', ?, ?)
            """,
            (stamp, stamp),
        )
        con.commit()
    finally:
        con.close()


def main() -> int:
    db = Database(_tmp / "phase19.db")

    print("=== 1) Additive projects.config_json column ===")
    cols = _project_columns(db)
    assert "config_json" in cols
    assert "modules_json" in cols
    assert "binder_properties_json" in cols
    print("  [PASS] config_json exists alongside existing project metadata JSON")

    print("\n=== 2) Existing project with no config metadata ===")
    proj = db.create_project(work_name="Phase 19 no-config project")
    p = db.get_project(proj.id)
    assert p is not None and p.config_json is None
    cfg = db.load_project_config(proj.id)
    assert cfg.profile.key == PROFILE_DEFAULT
    assert cfg.metadata.fallback_used is False
    assert db.validate_project_config(proj.id).ok
    print("  [PASS] NULL config_json loads as default profile without warning")

    print("\n=== 3) Attach and restore project profile metadata ===")
    attached = db.attach_project_config(proj.id, profile_key=PROFILE_CONSULTANCY)
    assert attached is not None
    assert attached.profile.key == PROFILE_CONSULTANCY
    loaded = db.load_project_config(proj.id)
    assert loaded.profile.key == PROFILE_CONSULTANCY
    assert loaded.report_metadata_enabled is True
    payload = _project_config_json(db, proj.id)
    assert payload["profile"] == PROFILE_CONSULTANCY
    assert payload["schema_version"] == CONFIG_SCHEMA_VERSION
    assert payload["config_version"] == CONFIG_SCHEMA_VERSION
    assert payload["created_at"]
    assert payload["updated_at"]
    assert payload["validation"]["ok"] is True
    assert payload["validation"]["issues"] == []
    created_at = payload["created_at"]

    db.attach_project_config(proj.id, profile_key=PROFILE_LAB)
    payload2 = _project_config_json(db, proj.id)
    assert payload2["profile"] == PROFILE_LAB
    assert payload2["created_at"] == created_at
    assert payload2["updated_at"]
    assert db.load_project_config(proj.id).profile.key == PROFILE_LAB
    print("  [PASS] profile round-trips; created_at preserved on update")

    print("\n=== 4) Unknown profile falls back with traceable warning ===")
    bad = db.create_project(work_name="Phase 19 unsupported profile")
    bad_cfg = db.attach_project_config(bad.id, profile_key="field-office")
    assert bad_cfg is not None
    assert bad_cfg.profile.key == PROFILE_DEFAULT
    assert bad_cfg.metadata.requested_profile == "field-office"
    assert bad_cfg.metadata.fallback_used is True
    assert bad_cfg.metadata.validation_issues
    loaded_bad_cfg = db.load_project_config(bad.id)
    assert loaded_bad_cfg.profile.key == PROFILE_DEFAULT
    assert loaded_bad_cfg.metadata.requested_profile == "field-office"
    assert loaded_bad_cfg.metadata.fallback_used is True
    assert loaded_bad_cfg.metadata.validation_issues
    assert db.validate_project_config(bad.id).ok
    bad_payload = _project_config_json(db, bad.id)
    assert bad_payload["profile"] == "field-office"
    assert bad_payload["resolved_profile"] == PROFILE_DEFAULT
    assert bad_payload["metadata"]["requested_profile"] == "field-office"
    assert bad_payload["metadata"]["fallback_used"] is True
    assert bad_payload["validation"]["issues"]
    print("  [PASS] unsupported profile persisted as default with warning metadata")

    print("\n=== 5) Malformed stored JSON is safe ===")
    malformed = db.create_project(work_name="Phase 19 malformed config")
    db.update_project(malformed.id, config_json="{not-json")
    malformed_cfg = db.load_project_config(malformed.id)
    assert malformed_cfg.profile.key == PROFILE_DEFAULT
    assert malformed_cfg.metadata.fallback_used is True
    assert malformed_cfg.metadata.validation_issues
    assert db.validate_project_config(malformed.id).ok
    print("  [PASS] malformed config_json falls back to default with warning metadata")

    print("\n=== 6) Legacy DB migration preserves old project records ===")
    legacy_path = _tmp / "phase19_legacy.db"
    _create_legacy_db(legacy_path)
    legacy_db = Database(legacy_path)
    legacy_cols = _project_columns(legacy_db)
    for expected in ("modules_json", "binder_grade", "binder_properties_json", "config_json"):
        assert expected in legacy_cols, f"legacy migration missing {expected}"
    legacy_cfg = legacy_db.load_project_config(1)
    assert legacy_cfg.profile.key == PROFILE_DEFAULT
    assert legacy_cfg.metadata.fallback_used is False
    assert legacy_db.validate_project_config(1).ok

    demo_cfg = legacy_db.attach_project_config(1, profile_key=PROFILE_DEMO)
    assert demo_cfg is not None and demo_cfg.profile.key == PROFILE_DEMO
    assert legacy_db.load_project_config(1).profile.sample_data_enabled is True
    print("  [PASS] legacy project migrated, then stores/restores demo profile")

    print("\nPHASE 19 PROJECT CONFIG PERSISTENCE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
