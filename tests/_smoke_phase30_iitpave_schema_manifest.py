"""Phase-30 smoke - IITPAVE fixture schema manifest audit summary."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEFAULT_FIXTURE_MANIFEST,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_VERIFIED,
    IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE,
    IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE,
    IITPAVE_SCHEMA_MANIFEST_STATUS_AUDIT_READY,
    IITPAVE_SCHEMA_MANIFEST_STATUS_BLOCKED_UNKNOWN_SCHEMA,
    IITPAVE_SCHEMA_MANIFEST_STATUS_NO_FIXTURES,
    IITPAVE_SCHEMA_MANIFEST_STATUS_NO_VERIFIED_FIXTURES,
    build_iitpave_fixture_schema_manifest,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase30_iitpave_schema_manifest_"))


def _write_manifest(folder: Path, fixtures: list[dict]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({"fixtures": fixtures}, indent=2),
        encoding="utf-8",
    )


def _write_fixture(folder: Path, name: str, lines: list[str]) -> Path:
    path = folder / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    print("=== 1) Complete reviewed fixture coverage is audit-ready only ===")
    ready_dir = _tmp / "ready"
    ready_dir.mkdir()
    direct = _write_fixture(ready_dir, "direct_stress_strain.out", [
        "IITPAVE OUTPUT",
        "IRC 37 flexible pavement analysis",
        "",
        "Stress and Strain table",
        "Layer Radius Value",
        "1 0.0 12.3",
        "2 155.0 45.6",
    ])
    elastic = _write_fixture(ready_dir, "elastic_stress_strain.out", [
        "IIT PAVE PROGRAM",
        "Elastic Layer Analysis",
        "Critical Strain Results",
        "Layer Depth Radius",
        "1 50 0",
        "2 250 155",
    ])
    _write_manifest(ready_dir, [
        {"filename": direct.name, "verification_status": FIXTURE_STATUS_VERIFIED},
        {"filename": elastic.name, "verification_status": FIXTURE_STATUS_VERIFIED},
    ])

    ready = build_iitpave_fixture_schema_manifest(ready_dir)
    assert ready.status == IITPAVE_SCHEMA_MANIFEST_STATUS_AUDIT_READY
    assert ready.parser_audit_ready is True
    assert ready.engineering_calculations_allowed is False
    assert ready.total_fixture_count == 2
    assert ready.verified_fixture_count == 2
    assert ready.mapped_schema_count == 2
    assert ready.blocked_schema_count == 0
    families = {item.schema_family: item.fixture_count for item in ready.family_coverage}
    assert families[IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE] == 1
    assert families[IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE] == 1
    assert any("engineering calculations remain blocked" in s for s in ready.audit_summary)
    print("  [PASS] reviewed schema families summarize as audit-ready only")

    print("\n=== 2) Unknown verified schema blocks manifest readiness ===")
    blocked_dir = _tmp / "blocked"
    blocked_dir.mkdir()
    mapped = _write_fixture(blocked_dir, "mapped.out", [
        "IITPAVE OUTPUT",
        "Stress and Strain table",
        "Layer Radius Value",
        "1 0.0 12.3",
    ])
    unknown = _write_fixture(blocked_dir, "unknown.out", [
        "IITPAVE OUTPUT",
        "Elastic Layer Profile",
        "Layer Depth Radius",
        "1 50 0",
    ])
    unsupported = _write_fixture(blocked_dir, "unsupported.out", [
        "random console log",
        "abc def",
    ])
    pending = _write_fixture(blocked_dir, "pending_review.out", [
        "IITPAVE OUTPUT",
        "Stress and Strain table",
        "1 2 3",
    ])
    _write_manifest(blocked_dir, [
        {"filename": mapped.name, "verification_status": FIXTURE_STATUS_VERIFIED},
        {"filename": unknown.name, "verification_status": FIXTURE_STATUS_VERIFIED},
        {"filename": unsupported.name, "verification_status": FIXTURE_STATUS_VERIFIED},
        {"filename": pending.name, "verification_status": FIXTURE_STATUS_OPERATOR_PENDING},
    ])

    blocked = build_iitpave_fixture_schema_manifest(blocked_dir)
    assert blocked.status == IITPAVE_SCHEMA_MANIFEST_STATUS_BLOCKED_UNKNOWN_SCHEMA
    assert blocked.parser_audit_ready is False
    assert blocked.engineering_calculations_allowed is False
    assert blocked.total_fixture_count == 4
    assert blocked.verified_fixture_count == 2
    assert blocked.mapped_schema_count == 1
    assert blocked.blocked_schema_count == 1
    assert blocked.unknown_schema_count == 1
    assert blocked.unsupported_schema_count == 1
    assert blocked.pending_review_count == 1
    assert any(e.blocked for e in blocked.entries if e.source_filename == unknown.name)
    print("  [PASS] unknown and unsupported fixture states are counted and blocked")

    print("\n=== 3) Empty and pending-only fixture folders are safe blocked states ===")
    empty_dir = _tmp / "empty"
    empty_dir.mkdir()
    empty = build_iitpave_fixture_schema_manifest(empty_dir)
    assert empty.status == IITPAVE_SCHEMA_MANIFEST_STATUS_NO_FIXTURES
    assert empty.parser_audit_ready is False

    pending_dir = _tmp / "pending"
    pending_dir.mkdir()
    pending_only = _write_fixture(pending_dir, "pending_only.out", [
        "IITPAVE OUTPUT",
        "Stress and Strain table",
        "1 2 3",
    ])
    _write_manifest(pending_dir, [{
        "filename": pending_only.name,
        "verification_status": FIXTURE_STATUS_OPERATOR_PENDING,
    }])
    pending_manifest = build_iitpave_fixture_schema_manifest(pending_dir)
    assert pending_manifest.status == IITPAVE_SCHEMA_MANIFEST_STATUS_NO_VERIFIED_FIXTURES
    assert pending_manifest.parser_audit_ready is False
    assert pending_manifest.pending_review_count == 1
    print("  [PASS] missing verified coverage never enables parser readiness")

    print("\n=== 4) Serialization stays audit-only and diagnostics-rich ===")
    payload = ready.as_dict()
    blocked_payload = blocked.as_dict()
    serialized = json.dumps({"ready": payload, "blocked": blocked_payload}).lower()
    assert "audit_summary" in serialized
    assert "family_coverage" in serialized
    assert "engineering_calculations_allowed" in serialized
    assert "fatigue" not in serialized
    assert "rutting" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    assert payload["engineering_calculations_allowed"] is False
    assert blocked_payload["engineering_calculations_allowed"] is False
    print("  [PASS] manifest serialization reports coverage without calculations")

    print("\nPHASE 30 IITPAVE SCHEMA MANIFEST SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
