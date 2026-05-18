"""Verified IITPAVE output fixture intake and parser-contract harness.

Phase 26 creates an audit trail for operator-provided output samples. It does
not ship real IITPAVE fixtures, invent a real output schema, parse real output,
extract strains, or make IRC:37 compliance claims.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)

from .discovery import IITPaveEnvironmentIssue
from .output_contract import (
    IITPAVE_OUTPUT_STATUS_EMPTY,
    IITPAVE_OUTPUT_STATUS_MISSING,
    IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
    IITPAVE_OUTPUT_STATUS_STUB_CONTRACT,
    IITPAVE_OUTPUT_STATUS_UNREADABLE,
    IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
    IITPaveOutputContractResult,
    inspect_iitpave_output_contract,
)


FIXTURE_STATUS_UNVERIFIED = "unverified"
FIXTURE_STATUS_OPERATOR_PENDING = "operator_provided_pending_review"
FIXTURE_STATUS_VERIFIED = "verified_contract_sample"
FIXTURE_STATUS_REJECTED = "rejected_unsupported"

SUPPORTED_FIXTURE_STATUSES = (
    FIXTURE_STATUS_UNVERIFIED,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_VERIFIED,
    FIXTURE_STATUS_REJECTED,
)

DEFAULT_FIXTURE_MANIFEST = "iitpave_fixture_manifest.json"
DEFAULT_OUTPUT_SUFFIXES = (".out", ".txt", ".dat", ".log")


@dataclass(frozen=True, slots=True)
class IITPaveFixtureRecord:
    source_path: str
    source_filename: str
    byte_size: int
    line_count: int
    checksum_sha256: str
    intake_timestamp_utc: str
    verification_status: str
    contract_status: str
    contract_format: str
    detected_markers: tuple[str, ...] = ()
    rejected_reason: str = ""
    contract: IITPaveOutputContractResult | None = None
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def accepted_for_contract_review(self) -> bool:
        return self.verification_status in (
            FIXTURE_STATUS_OPERATOR_PENDING,
            FIXTURE_STATUS_VERIFIED,
        )

    @property
    def verified(self) -> bool:
        return self.verification_status == FIXTURE_STATUS_VERIFIED

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_filename": self.source_filename,
            "byte_size": self.byte_size,
            "line_count": self.line_count,
            "checksum_sha256": self.checksum_sha256,
            "intake_timestamp_utc": self.intake_timestamp_utc,
            "verification_status": self.verification_status,
            "contract_status": self.contract_status,
            "contract_format": self.contract_format,
            "detected_markers": list(self.detected_markers),
            "rejected_reason": self.rejected_reason,
            "accepted_for_contract_review": self.accepted_for_contract_review,
            "verified": self.verified,
            "contract": self.contract.as_dict() if self.contract else None,
            "issues": [i.as_dict() for i in self.issues],
        }


@dataclass(frozen=True, slots=True)
class IITPaveFixtureIntakeResult:
    fixture_dir: str
    missing_folder: bool
    records: tuple[IITPaveFixtureRecord, ...] = ()
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.severity == VALIDATION_ERROR for i in self.issues)

    @property
    def verified_records(self) -> tuple[IITPaveFixtureRecord, ...]:
        return tuple(r for r in self.records if r.verified)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fixture_dir": self.fixture_dir,
            "missing_folder": self.missing_folder,
            "record_count": len(self.records),
            "verified_count": len(self.verified_records),
            "records": [r.as_dict() for r in self.records],
            "issues": [i.as_dict() for i in self.issues],
        }


@dataclass(frozen=True, slots=True)
class IITPaveParserContractHarnessResult:
    intake: IITPaveFixtureIntakeResult
    verified_count: int
    parser_contract_ready: bool
    blocked: bool
    blocked_reason: str
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and self.parser_contract_ready

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verified_count": self.verified_count,
            "parser_contract_ready": self.parser_contract_ready,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "intake": self.intake.as_dict(),
            "issues": [i.as_dict() for i in self.issues],
        }


def _utc_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _line_count(raw: bytes) -> int:
    return raw.decode("utf-8", errors="replace").count("\n") + (
        1 if raw and not raw.endswith(b"\n") else 0
    )


def _manifest_statuses(fixture_dir: Path, manifest_name: str) -> dict[str, str]:
    path = fixture_dir / manifest_name
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("fixtures") if isinstance(payload, Mapping) else None
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return {}
    out: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        filename = str(item.get("filename") or "").strip()
        status = str(item.get("verification_status") or "").strip()
        if filename and status in SUPPORTED_FIXTURE_STATUSES:
            out[filename] = status
    return out


def _status_from_contract(
    contract: IITPaveOutputContractResult,
    requested_status: str,
) -> tuple[str, str]:
    if contract.status in (
        IITPAVE_OUTPUT_STATUS_MISSING,
        IITPAVE_OUTPUT_STATUS_UNREADABLE,
        IITPAVE_OUTPUT_STATUS_EMPTY,
        IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
    ):
        return FIXTURE_STATUS_REJECTED, contract.blocked_reason
    if contract.status == IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING:
        if requested_status == FIXTURE_STATUS_VERIFIED:
            return FIXTURE_STATUS_VERIFIED, ""
        if requested_status == FIXTURE_STATUS_UNVERIFIED:
            return FIXTURE_STATUS_UNVERIFIED, ""
        return FIXTURE_STATUS_OPERATOR_PENDING, ""
    if contract.status == IITPAVE_OUTPUT_STATUS_STUB_CONTRACT:
        if requested_status == FIXTURE_STATUS_REJECTED:
            return FIXTURE_STATUS_REJECTED, "Fixture was manually rejected."
        return requested_status if requested_status else FIXTURE_STATUS_UNVERIFIED, ""
    return FIXTURE_STATUS_REJECTED, contract.blocked_reason or "Unsupported output contract."


def intake_iitpave_output_fixture(
    path: Path | str,
    *,
    verification_status: str = FIXTURE_STATUS_OPERATOR_PENDING,
    intake_timestamp_utc: str | None = None,
) -> IITPaveFixtureRecord:
    """Capture metadata for one operator-provided IITPAVE output sample."""
    source = Path(path)
    requested = (
        verification_status
        if verification_status in SUPPORTED_FIXTURE_STATUSES
        else FIXTURE_STATUS_OPERATOR_PENDING
    )
    contract = inspect_iitpave_output_contract(path=source)
    issues = list(contract.issues)
    try:
        raw = source.read_bytes() if source.is_file() else b""
    except OSError:
        raw = b""

    status, rejected_reason = _status_from_contract(contract, requested)
    if status == FIXTURE_STATUS_VERIFIED and contract.status != IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING:
        status = FIXTURE_STATUS_REJECTED
        rejected_reason = (
            "Only operator-reviewed real IITPAVE output samples may be marked "
            "verified_contract_sample."
        )
        issues.append(_issue(VALIDATION_ERROR, "fixture.verification_status", rejected_reason))
    elif status == FIXTURE_STATUS_VERIFIED:
        issues.append(_issue(
            VALIDATION_WARNING,
            "fixture.verification_status",
            "Fixture is marked verified for contract review, but real parsing remains disabled.",
        ))
    elif status == FIXTURE_STATUS_OPERATOR_PENDING:
        issues.append(_issue(
            VALIDATION_INFO,
            "fixture.verification_status",
            "Fixture is operator-provided and pending review; real parsing remains disabled.",
        ))

    return IITPaveFixtureRecord(
        source_path=str(source),
        source_filename=source.name,
        byte_size=len(raw),
        line_count=_line_count(raw),
        checksum_sha256=_sha256(raw) if raw else "",
        intake_timestamp_utc=intake_timestamp_utc or _utc_iso(),
        verification_status=status,
        contract_status=contract.status,
        contract_format=contract.format_key,
        detected_markers=contract.markers,
        rejected_reason=rejected_reason,
        contract=contract,
        issues=tuple(issues),
    )


def intake_iitpave_fixture_folder(
    fixture_dir: Path | str,
    *,
    manifest_name: str = DEFAULT_FIXTURE_MANIFEST,
    suffixes: tuple[str, ...] = DEFAULT_OUTPUT_SUFFIXES,
    intake_timestamp_utc: str | None = None,
) -> IITPaveFixtureIntakeResult:
    """Scan a folder of operator-provided IITPAVE output samples."""
    root = Path(fixture_dir)
    if not root.is_dir():
        msg = f"IITPAVE fixture folder does not exist: {root}"
        return IITPaveFixtureIntakeResult(
            fixture_dir=str(root),
            missing_folder=True,
            issues=(_issue(VALIDATION_WARNING, "fixture_dir", msg),),
        )

    manifest_status = _manifest_statuses(root, manifest_name)
    records: list[IITPaveFixtureRecord] = []
    for candidate in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not candidate.is_file():
            continue
        if candidate.name == manifest_name:
            continue
        if suffixes and candidate.suffix.lower() not in suffixes:
            continue
        records.append(intake_iitpave_output_fixture(
            candidate,
            verification_status=manifest_status.get(
                candidate.name,
                FIXTURE_STATUS_OPERATOR_PENDING,
            ),
            intake_timestamp_utc=intake_timestamp_utc,
        ))

    issues: list[IITPaveEnvironmentIssue] = []
    if not records:
        issues.append(_issue(
            VALIDATION_INFO,
            "fixture_dir",
            "No IITPAVE output fixture files were found.",
        ))
    return IITPaveFixtureIntakeResult(
        fixture_dir=str(root),
        missing_folder=False,
        records=tuple(records),
        issues=tuple(issues),
    )


def run_iitpave_parser_contract_harness(
    fixture_dir: Path | str,
    *,
    manifest_name: str = DEFAULT_FIXTURE_MANIFEST,
) -> IITPaveParserContractHarnessResult:
    """Evaluate fixture availability for future real-output parser contracts."""
    intake = intake_iitpave_fixture_folder(fixture_dir, manifest_name=manifest_name)
    issues: list[IITPaveEnvironmentIssue] = list(intake.issues)
    verified = intake.verified_records
    if not verified:
        reason = (
            "No verified real IITPAVE output fixture is available; parser "
            "contract tests are safely blocked."
        )
        issues.append(_issue(VALIDATION_WARNING, "fixture.verification_status", reason))
        return IITPaveParserContractHarnessResult(
            intake=intake,
            verified_count=0,
            parser_contract_ready=False,
            blocked=True,
            blocked_reason=reason,
            issues=tuple(issues),
        )

    reason = (
        "Verified fixture metadata exists, but the real IITPAVE parser contract "
        "is not implemented yet; parsing remains blocked."
    )
    issues.append(_issue(VALIDATION_WARNING, "parser_contract", reason))
    return IITPaveParserContractHarnessResult(
        intake=intake,
        verified_count=len(verified),
        parser_contract_ready=False,
        blocked=True,
        blocked_reason=reason,
        issues=tuple(issues),
    )
