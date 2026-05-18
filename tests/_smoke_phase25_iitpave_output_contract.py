"""Phase-25 smoke - IITPAVE output contract detection guardrails."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.core import (
    IITPAVE_OUTPUT_FORMAT_REAL_PENDING,
    IITPAVE_OUTPUT_FORMAT_STUB,
    IITPAVE_OUTPUT_STATUS_EMPTY,
    IITPAVE_OUTPUT_STATUS_MISSING,
    IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
    IITPAVE_OUTPUT_STATUS_STUB_CONTRACT,
    IITPAVE_OUTPUT_STATUS_UNREADABLE,
    IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
    IITPAVE_STUB_OUTPUT_VERSION,
    inspect_iitpave_output_contract,
)


_tmp = Path(tempfile.mkdtemp(prefix="phase25_iitpave_output_"))


def main() -> int:
    print("=== 1) Missing output is blocked ===")
    missing = inspect_iitpave_output_contract(path=_tmp / "missing.out")
    assert missing.status == IITPAVE_OUTPUT_STATUS_MISSING
    assert missing.parse_allowed is False
    assert missing.blocked is True
    assert missing.ok is False
    assert "does not exist" in missing.blocked_reason
    assert missing.as_dict()["blocked"] is True
    print("  [PASS] missing file classified without parser use")

    print("\n=== 2) Empty output is blocked ===")
    empty_path = _tmp / "empty.out"
    empty_path.write_text("", encoding="utf-8")
    empty = inspect_iitpave_output_contract(path=empty_path)
    assert empty.status == IITPAVE_OUTPUT_STATUS_EMPTY
    assert empty.byte_count == 0
    assert empty.parse_allowed is False
    print("  [PASS] empty output refuses parsing")

    print("\n=== 3) Non-file and unreadable-ish paths are blocked ===")
    directory = inspect_iitpave_output_contract(path=_tmp)
    assert directory.status == IITPAVE_OUTPUT_STATUS_UNREADABLE
    assert directory.parse_allowed is False
    invalid = inspect_iitpave_output_contract(path="\0bad-output-path")
    assert invalid.status == IITPAVE_OUTPUT_STATUS_UNREADABLE
    assert "embedded null byte" in invalid.blocked_reason
    print("  [PASS] directory and invalid path become guardrail errors")

    print("\n=== 4) Unknown output text is unsupported and blocked ===")
    unknown = inspect_iitpave_output_contract(
        text="some random console output\n1 2 3\n"
    )
    assert unknown.status == IITPAVE_OUTPUT_STATUS_UNSUPPORTED
    assert unknown.parse_allowed is False
    assert any(i.severity == "error" for i in unknown.issues)
    print("  [PASS] unknown text cannot silently reach parser")

    print("\n=== 5) IITPAVE-like real output is pending, not invented ===")
    realish = inspect_iitpave_output_contract(
        text="IITPAVE analysis complete\nStress and Strain table follows\n"
    )
    assert realish.status == IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING
    assert realish.format_key == IITPAVE_OUTPUT_FORMAT_REAL_PENDING
    assert realish.parse_allowed is False
    assert realish.has_warnings is True
    assert "no verified real IITPAVE output contract" in realish.blocked_reason
    print("  [PASS] real-looking output is explicitly pending schema verification")

    print("\n=== 6) Project-owned stub marker is recognized only as placeholder contract ===")
    stub_text = (
        f"# pavement_lab iitpave stub output ({IITPAVE_STUB_OUTPUT_VERSION})\n"
        "# PLACEHOLDER values - no real IITPAVE engineering output\n"
        "0\n"
    )
    stub = inspect_iitpave_output_contract(text=stub_text)
    assert stub.status == IITPAVE_OUTPUT_STATUS_STUB_CONTRACT
    assert stub.format_key == IITPAVE_OUTPUT_FORMAT_STUB
    assert stub.parse_allowed is True
    assert stub.parser_source == "stub"
    assert IITPAVE_STUB_OUTPUT_VERSION in stub.markers
    assert stub.ok is True
    print("  [PASS] known stub contract is traceable and placeholder-only")

    print("\n=== 7) Output file path round-trip preserves metadata ===")
    stub_path = _tmp / "stub.out"
    stub_path.write_text(stub_text, encoding="utf-8")
    from_file = inspect_iitpave_output_contract(path=stub_path)
    assert from_file.status == IITPAVE_OUTPUT_STATUS_STUB_CONTRACT
    assert from_file.source_path == str(stub_path)
    assert from_file.byte_count == len(stub_path.read_bytes())
    assert from_file.line_count == 3
    payload = from_file.as_dict()
    assert payload["source_path"] == str(stub_path)
    assert payload["markers"]
    print("  [PASS] file inspection is audit-serializable")

    print("\nPHASE 25 IITPAVE OUTPUT CONTRACT SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
