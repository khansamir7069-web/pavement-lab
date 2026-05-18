"""Phase-28 smoke - guarded IITPAVE verified-fixture schema mapping."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEFAULT_FIXTURE_MANIFEST,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_UNVERIFIED,
    FIXTURE_STATUS_VERIFIED,
    IITPAVE_SCHEMA_MAPPING_STATUS_BLOCKED,
    IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED,
    IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN,
    IITPAVE_SCHEMA_SECTION_OUTPUT_HEADER,
    IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_CONTEXT,
    IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE,
    map_iitpave_verified_fixture_schema,
    intake_iitpave_fixture_folder,
    intake_iitpave_output_fixture,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase28_iitpave_schema_mapping_"))


def _write_manifest(folder: Path, fixtures: list[dict]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({"fixtures": fixtures}, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    print("=== 1) Unverified fixture cannot be schema-mapped ===")
    fixtures = _tmp / "fixtures"
    fixtures.mkdir()
    unverified_path = fixtures / "operator_unverified.out"
    unverified_path.write_text(
        "IITPAVE analysis complete\nStress and Strain table follows\n1 2 3\n",
        encoding="utf-8",
    )
    unverified = intake_iitpave_output_fixture(
        unverified_path,
        verification_status=FIXTURE_STATUS_UNVERIFIED,
    )
    blocked = map_iitpave_verified_fixture_schema(unverified)
    assert blocked.blocked is True
    assert blocked.status == IITPAVE_SCHEMA_MAPPING_STATUS_BLOCKED
    assert "parser-contract" in blocked.blocked_reason
    assert blocked.engineering_values_extracted is False
    print("  [PASS] schema mapping consumes only verified fixture records")

    print("\n=== 2) Verified reviewed structure maps to audit schema roles ===")
    verified_path = fixtures / "operator_verified.out"
    verified_path.write_text(
        "\n".join([
            "IITPAVE OUTPUT",
            "IRC 37 flexible pavement analysis",
            "",
            "Stress and Strain table",
            "Layer   Radius   Value",
            "1       0.0      12.3",
            "2       155.0    45.6",
            "",
        ]),
        encoding="utf-8",
    )
    _write_manifest(fixtures, [{
        "filename": verified_path.name,
        "verification_status": FIXTURE_STATUS_VERIFIED,
    }])
    intake = intake_iitpave_fixture_folder(fixtures)
    verified = next(r for r in intake.records if r.source_filename == verified_path.name)
    mapped = map_iitpave_verified_fixture_schema(verified)
    assert mapped.blocked is False
    assert mapped.ok is True
    assert mapped.status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED
    assert mapped.engineering_values_extracted is False
    roles = {m.schema_role for m in mapped.mappings}
    assert IITPAVE_SCHEMA_SECTION_OUTPUT_HEADER in roles
    assert IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_CONTEXT in roles
    assert IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE in roles
    assert mapped.as_dict()["engineering_values_extracted"] is False
    print("  [PASS] verified fixture maps sections without engineering values")

    print("\n=== 3) Unknown or partial schema remains blocked ===")
    unknown_path = fixtures / "operator_unknown.out"
    unknown_path.write_text(
        "IITPAVE summary\nStress and Strain heading without numeric table\n",
        encoding="utf-8",
    )
    unknown = intake_iitpave_output_fixture(
        unknown_path,
        verification_status=FIXTURE_STATUS_VERIFIED,
    )
    unknown_mapping = map_iitpave_verified_fixture_schema(unknown)
    assert unknown_mapping.blocked is True
    assert unknown_mapping.status == IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN
    assert "schema" in unknown_mapping.blocked_reason.lower()
    assert unknown_mapping.engineering_values_extracted is False
    print("  [PASS] partial schema is not promoted to parsing")

    print("\n=== 4) Unsupported output cannot be mapped ===")
    unsupported_path = fixtures / "operator_unsupported.out"
    unsupported_path.write_text("random console log\nabc def\n", encoding="utf-8")
    unsupported = intake_iitpave_output_fixture(
        unsupported_path,
        verification_status=FIXTURE_STATUS_OPERATOR_PENDING,
    )
    unsupported_mapping = map_iitpave_verified_fixture_schema(unsupported)
    assert unsupported_mapping.blocked is True
    assert unsupported_mapping.status == IITPAVE_SCHEMA_MAPPING_STATUS_BLOCKED
    print("  [PASS] unsupported contract remains blocked")

    print("\n=== 5) Mappings contain no strain or compliance payload ===")
    payload = mapped.as_dict()
    forbidden = json.dumps(payload).lower()
    assert "fatigue" not in forbidden
    assert "rutting" not in forbidden
    assert "irc_compliance" not in forbidden
    for mapping in mapped.mappings:
        assert mapping.values_extracted is False
    print("  [PASS] no engineering calculations or compliance claims are emitted")

    print("\nPHASE 28 IITPAVE SCHEMA MAPPING SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
