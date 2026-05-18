"""Phase-26 smoke - IITPAVE output fixture intake and harness."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEFAULT_FIXTURE_MANIFEST,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_REJECTED,
    FIXTURE_STATUS_UNVERIFIED,
    IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
    IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
    intake_iitpave_fixture_folder,
    intake_iitpave_output_fixture,
    run_iitpave_parser_contract_harness,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase26_iitpave_fixture_"))


def _write_manifest(folder: Path, fixtures: list[dict]) -> None:
    (folder / DEFAULT_FIXTURE_MANIFEST).write_text(
        json.dumps({"fixtures": fixtures}, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    print("=== 1) Missing fixture folder is a safe skip/block ===")
    missing_dir = _tmp / "missing"
    missing = intake_iitpave_fixture_folder(missing_dir)
    assert missing.missing_folder is True
    assert missing.records == ()
    assert missing.ok is True
    assert any("does not exist" in i.message for i in missing.issues)
    print("  [PASS] missing folder returns warning-only intake result")

    print("\n=== 2) Unverified operator sample is classified without parsing ===")
    fixtures = _tmp / "fixtures"
    fixtures.mkdir()
    realish = fixtures / "operator_realish.out"
    realish_text = "IITPAVE analysis complete\nStress and Strain table follows\n"
    realish.write_text(realish_text, encoding="utf-8")
    _write_manifest(fixtures, [{
        "filename": realish.name,
        "verification_status": FIXTURE_STATUS_UNVERIFIED,
    }])
    intake = intake_iitpave_fixture_folder(fixtures, intake_timestamp_utc="2026-05-18T00:00:00Z")
    assert len(intake.records) == 1
    rec = intake.records[0]
    assert rec.source_filename == realish.name
    assert rec.byte_size == len(realish.read_bytes())
    assert rec.line_count == 2
    assert len(rec.checksum_sha256) == 64
    assert rec.intake_timestamp_utc == "2026-05-18T00:00:00Z"
    assert rec.verification_status == FIXTURE_STATUS_UNVERIFIED
    assert rec.contract_status == IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING
    assert rec.detected_markers
    assert rec.as_dict()["checksum_sha256"] == rec.checksum_sha256
    print("  [PASS] unverified operator sample captures metadata and markers")

    print("\n=== 3) Unsupported sample is rejected ===")
    bad = fixtures / "random_console.out"
    bad.write_text("random console output\n1 2 3\n", encoding="utf-8")
    bad_rec = intake_iitpave_output_fixture(
        bad,
        verification_status=FIXTURE_STATUS_OPERATOR_PENDING,
        intake_timestamp_utc="2026-05-18T00:00:00Z",
    )
    assert bad_rec.verification_status == FIXTURE_STATUS_REJECTED
    assert bad_rec.contract_status == IITPAVE_OUTPUT_STATUS_UNSUPPORTED
    assert "unsupported" in bad_rec.rejected_reason.lower()
    print("  [PASS] unsupported output cannot enter pending review")

    print("\n=== 4) No verified real fixture available blocks parser harness ===")
    harness = run_iitpave_parser_contract_harness(fixtures)
    assert harness.blocked is True
    assert harness.parser_contract_ready is False
    assert harness.verified_count == 0
    assert "No verified real IITPAVE output fixture" in harness.blocked_reason
    assert harness.as_dict()["blocked"] is True
    print("  [PASS] parser contract harness safely blocks without verified fixtures")

    print("\n=== 5) Folder scan includes pending sample and rejected sample ===")
    scan = intake_iitpave_fixture_folder(fixtures)
    statuses = {r.source_filename: r.verification_status for r in scan.records}
    assert statuses[realish.name] == FIXTURE_STATUS_UNVERIFIED
    assert statuses[bad.name] == FIXTURE_STATUS_REJECTED
    assert scan.as_dict()["record_count"] == 2
    print("  [PASS] folder scan is audit-serializable")

    print("\nPHASE 26 IITPAVE FIXTURE INTAKE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
