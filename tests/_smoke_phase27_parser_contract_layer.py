"""Phase-27 smoke - conservative IITPAVE parser-contract layer."""
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
    IITPAVE_PARSER_CONTRACT_STATUS_BLOCKED,
    IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL,
    IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED,
    IITPAVE_PARSER_CONTRACT_STATUS_UNSUPPORTED,
    IITPAVE_SECTION_HEADER,
    IITPAVE_SECTION_LABELED_BLOCK,
    IITPAVE_SECTION_TABLE_LIKE,
    inspect_iitpave_verified_parser_contract,
    intake_iitpave_fixture_folder,
    intake_iitpave_output_fixture,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase27_iitpave_parser_contract_"))


def _write_manifest(folder: Path, fixtures: list[dict]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({"fixtures": fixtures}, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    print("=== 1) Unverified operator sample is rejected ===")
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
    unverified_contract = inspect_iitpave_verified_parser_contract(unverified)
    assert unverified_contract.blocked is True
    assert unverified_contract.status == IITPAVE_PARSER_CONTRACT_STATUS_BLOCKED
    assert "verified_contract_sample" in unverified_contract.blocked_reason
    assert unverified_contract.engineering_values_extracted is False
    print("  [PASS] unverified metadata cannot reach section inspection")

    print("\n=== 2) Verified fixture exposes sections only ===")
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
    accepted = inspect_iitpave_verified_parser_contract(verified)
    assert accepted.blocked is False
    assert accepted.ok is True
    assert accepted.status == IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED
    assert accepted.engineering_values_extracted is False
    section_types = {s.section_type for s in accepted.sections}
    assert IITPAVE_SECTION_HEADER in section_types
    assert IITPAVE_SECTION_LABELED_BLOCK in section_types
    assert IITPAVE_SECTION_TABLE_LIKE in section_types
    assert accepted.markers
    assert accepted.as_dict()["engineering_values_extracted"] is False
    print("  [PASS] verified fixture yields audit-only sections and markers")

    print("\n=== 3) Unsupported contract is blocked ===")
    unsupported_path = fixtures / "operator_unsupported.out"
    unsupported_path.write_text("random console log\nabc def\n", encoding="utf-8")
    unsupported = intake_iitpave_output_fixture(
        unsupported_path,
        verification_status=FIXTURE_STATUS_OPERATOR_PENDING,
    )
    unsupported_contract = inspect_iitpave_verified_parser_contract(unsupported)
    assert unsupported_contract.blocked is True
    assert unsupported_contract.status == IITPAVE_PARSER_CONTRACT_STATUS_UNSUPPORTED
    assert "unsupported" in unsupported_contract.blocked_reason.lower()
    print("  [PASS] unsupported output remains blocked")

    print("\n=== 4) Partial section detection is warning-only ===")
    partial_path = fixtures / "operator_partial.out"
    partial_path.write_text(
        "IITPAVE summary\nStress and Strain heading without numeric table\n",
        encoding="utf-8",
    )
    partial = intake_iitpave_output_fixture(
        partial_path,
        verification_status=FIXTURE_STATUS_VERIFIED,
    )
    partial_contract = inspect_iitpave_verified_parser_contract(partial)
    assert partial_contract.blocked is False
    assert partial_contract.status == IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL
    assert partial_contract.partial is True
    assert partial_contract.has_warnings is True
    assert partial_contract.engineering_values_extracted is False
    print("  [PASS] partial verified structure is surfaced with warnings")

    print("\n=== 5) No engineering values are extracted ===")
    for section in accepted.sections:
        payload = section.as_dict()
        assert "epsilon" not in payload
        assert "strain_value" not in payload
        assert "stress_value" not in payload
    payload = accepted.as_dict()
    assert payload["engineering_values_extracted"] is False
    assert "point_results" not in payload
    print("  [PASS] contract layer exposes no strain/stress calculations")

    print("\nPHASE 27 IITPAVE PARSER CONTRACT SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
