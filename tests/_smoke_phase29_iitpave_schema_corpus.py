"""Phase-29 smoke - reviewed IITPAVE fixture schema corpus coverage."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEFAULT_FIXTURE_MANIFEST,
    FIXTURE_STATUS_VERIFIED,
    IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE,
    IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE,
    IITPAVE_SCHEMA_FAMILY_UNKNOWN,
    IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED,
    IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN,
    IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE,
    intake_iitpave_fixture_folder,
    map_iitpave_verified_fixture_schema,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase29_iitpave_schema_corpus_"))


def _write_manifest(folder: Path, names: list[str]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({
            "fixtures": [
                {"filename": name, "verification_status": FIXTURE_STATUS_VERIFIED}
                for name in names
            ],
        }, indent=2),
        encoding="utf-8",
    )


def _write_fixture(folder: Path, name: str, lines: list[str]) -> Path:
    path = folder / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mapped_by_name(folder: Path) -> dict[str, object]:
    intake = intake_iitpave_fixture_folder(folder)
    assert intake.verified_records
    return {
        record.source_filename: map_iitpave_verified_fixture_schema(record)
        for record in intake.verified_records
    }


def main() -> int:
    print("=== 1) Reviewed direct stress/strain table variant maps ===")
    fixtures = _tmp / "fixtures"
    fixtures.mkdir()
    direct = _write_fixture(fixtures, "direct_stress_strain.out", [
        "IITPAVE OUTPUT",
        "IRC 37 flexible pavement analysis",
        "",
        "Stress and Strain table",
        "Layer Radius Value",
        "1 0.0 12.3",
        "2 155.0 45.6",
    ])
    elastic_split = _write_fixture(fixtures, "elastic_split_context.out", [
        "IIT PAVE PROGRAM",
        "Elastic Layer Analysis",
        "Critical Strain Results",
        "Layer Depth Radius",
        "1 50 0",
        "2 250 155",
    ])
    elastic_inline = _write_fixture(fixtures, "elastic_inline_context.out", [
        "IITPAVE OUTPUT",
        "Elastic Layer Stress Strain Output",
        "Layer Depth Radius",
        "1 75 0",
        "2 300 155",
    ])
    unknown = _write_fixture(fixtures, "unknown_layer_table.out", [
        "IITPAVE OUTPUT",
        "Elastic Layer Profile",
        "Layer Depth Radius",
        "1 50 0",
        "2 250 155",
    ])
    distant = _write_fixture(fixtures, "distant_table.out", [
        "IITPAVE OUTPUT",
        "Critical Strain Results",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "Layer Depth Radius",
        "1 50 0",
    ])
    _write_manifest(fixtures, [
        direct.name,
        elastic_split.name,
        elastic_inline.name,
        unknown.name,
        distant.name,
    ])

    mapped = _mapped_by_name(fixtures)
    direct_result = mapped[direct.name]
    assert direct_result.status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED
    assert direct_result.schema_family == IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE
    assert direct_result.engineering_values_extracted is False
    assert "table_candidate" in direct_result.classification_markers
    print("  [PASS] direct reviewed schema family remains audit-only")

    print("\n=== 2) Reviewed elastic-layer variants map conservatively ===")
    for path in (elastic_split, elastic_inline):
        result = mapped[path.name]
        assert result.status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED
        assert result.schema_family == (
            IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE
        )
        assert result.engineering_values_extracted is False
        roles = {m.schema_role for m in result.mappings}
        assert IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE in roles
        assert "elastic_layer_context" in result.classification_markers
    print("  [PASS] split and inline elastic-layer fixture variants are classified")

    print("\n=== 3) Unknown reviewed structures remain blocked ===")
    for path in (unknown, distant):
        result = mapped[path.name]
        assert result.blocked is True
        assert result.status == IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN
        assert result.schema_family == IITPAVE_SCHEMA_FAMILY_UNKNOWN
        assert result.engineering_values_extracted is False
        assert "schema" in result.blocked_reason.lower()
    print("  [PASS] unknown and distant-table schemas stay blocked")

    print("\n=== 4) Audit serialization carries classification, not calculations ===")
    payload = {
        name: result.as_dict()
        for name, result in mapped.items()
    }
    serialized = json.dumps(payload).lower()
    assert "schema_family" in serialized
    assert "classification_markers" in serialized
    assert "fatigue" not in serialized
    assert "rutting" not in serialized
    assert "irc_compliance" not in serialized
    assert "point_results" not in serialized
    print("  [PASS] schema corpus serialization remains diagnostic-only")

    print("\nPHASE 29 IITPAVE SCHEMA CORPUS SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
