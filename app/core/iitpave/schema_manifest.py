"""Audit manifest for reviewed IITPAVE fixture schema coverage.

Phase 30 summarizes verified fixture schema mapping status for operators. It
does not parse engineering values, compute mechanistic checks, or make IRC:37
compliance claims.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)

from .discovery import IITPaveEnvironmentIssue
from .fixture_intake import (
    DEFAULT_FIXTURE_MANIFEST,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_REJECTED,
    FIXTURE_STATUS_UNVERIFIED,
    FIXTURE_STATUS_VERIFIED,
    IITPaveFixtureIntakeResult,
    IITPaveFixtureRecord,
    intake_iitpave_fixture_folder,
)
from .output_contract import IITPAVE_OUTPUT_STATUS_UNSUPPORTED
from .schema_mapping import (
    IITPAVE_SCHEMA_FAMILY_UNKNOWN,
    IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED,
    IITPaveVerifiedFixtureSchemaMappingResult,
    map_iitpave_verified_fixture_schema,
)


IITPAVE_SCHEMA_MANIFEST_STATUS_NO_FIXTURES = "no_fixtures"
IITPAVE_SCHEMA_MANIFEST_STATUS_NO_VERIFIED_FIXTURES = "no_verified_fixtures"
IITPAVE_SCHEMA_MANIFEST_STATUS_BLOCKED_UNKNOWN_SCHEMA = "blocked_unknown_schema"
IITPAVE_SCHEMA_MANIFEST_STATUS_AUDIT_READY = "audit_ready_calculations_blocked"


@dataclass(frozen=True, slots=True)
class IITPaveSchemaFamilyCoverage:
    schema_family: str
    fixture_count: int
    source_filenames: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_family": self.schema_family,
            "fixture_count": self.fixture_count,
            "source_filenames": list(self.source_filenames),
        }


@dataclass(frozen=True, slots=True)
class IITPaveFixtureSchemaManifestEntry:
    source_filename: str
    verification_status: str
    contract_status: str
    schema_status: str = ""
    schema_family: str = IITPAVE_SCHEMA_FAMILY_UNKNOWN
    blocked: bool = True
    blocked_reason: str = ""
    mapping_count: int = 0
    classification_markers: tuple[str, ...] = ()
    engineering_values_extracted: bool = False
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()
    mapping: IITPaveVerifiedFixtureSchemaMappingResult | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_filename": self.source_filename,
            "verification_status": self.verification_status,
            "contract_status": self.contract_status,
            "schema_status": self.schema_status,
            "schema_family": self.schema_family,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "mapping_count": self.mapping_count,
            "classification_markers": list(self.classification_markers),
            "engineering_values_extracted": self.engineering_values_extracted,
            "issues": [i.as_dict() for i in self.issues],
            "mapping": self.mapping.as_dict() if self.mapping else None,
        }


@dataclass(frozen=True, slots=True)
class IITPaveFixtureSchemaManifest:
    intake: IITPaveFixtureIntakeResult
    status: str
    parser_audit_ready: bool
    engineering_calculations_allowed: bool
    entries: tuple[IITPaveFixtureSchemaManifestEntry, ...] = ()
    family_coverage: tuple[IITPaveSchemaFamilyCoverage, ...] = ()
    total_fixture_count: int = 0
    verified_fixture_count: int = 0
    mapped_schema_count: int = 0
    blocked_schema_count: int = 0
    unknown_schema_count: int = 0
    unsupported_schema_count: int = 0
    pending_review_count: int = 0
    unverified_count: int = 0
    rejected_count: int = 0
    audit_summary: tuple[str, ...] = ()
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.parser_audit_ready and not any(
            i.severity == VALIDATION_ERROR for i in self.issues
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "parser_audit_ready": self.parser_audit_ready,
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "total_fixture_count": self.total_fixture_count,
            "verified_fixture_count": self.verified_fixture_count,
            "mapped_schema_count": self.mapped_schema_count,
            "blocked_schema_count": self.blocked_schema_count,
            "unknown_schema_count": self.unknown_schema_count,
            "unsupported_schema_count": self.unsupported_schema_count,
            "pending_review_count": self.pending_review_count,
            "unverified_count": self.unverified_count,
            "rejected_count": self.rejected_count,
            "family_coverage": [c.as_dict() for c in self.family_coverage],
            "audit_summary": list(self.audit_summary),
            "entries": [e.as_dict() for e in self.entries],
            "intake": self.intake.as_dict(),
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _entry_for_unmapped_record(
    record: IITPaveFixtureRecord,
    reason: str,
) -> IITPaveFixtureSchemaManifestEntry:
    issues = tuple(record.issues) + (
        _issue(VALIDATION_INFO, "schema_manifest.record", reason),
    )
    return IITPaveFixtureSchemaManifestEntry(
        source_filename=record.source_filename,
        verification_status=record.verification_status,
        contract_status=record.contract_status,
        schema_status="not_evaluated",
        blocked=True,
        blocked_reason=reason,
        issues=issues,
    )


def _entry_for_verified_record(
    record: IITPaveFixtureRecord,
) -> IITPaveFixtureSchemaManifestEntry:
    mapping = map_iitpave_verified_fixture_schema(record)
    return IITPaveFixtureSchemaManifestEntry(
        source_filename=record.source_filename,
        verification_status=record.verification_status,
        contract_status=record.contract_status,
        schema_status=mapping.status,
        schema_family=mapping.schema_family,
        blocked=mapping.blocked,
        blocked_reason=mapping.blocked_reason,
        mapping_count=len(mapping.mappings),
        classification_markers=mapping.classification_markers,
        engineering_values_extracted=mapping.engineering_values_extracted,
        issues=mapping.issues,
        mapping=mapping,
    )


def _family_coverage(
    entries: tuple[IITPaveFixtureSchemaManifestEntry, ...],
) -> tuple[IITPaveSchemaFamilyCoverage, ...]:
    filenames: dict[str, list[str]] = {}
    for entry in entries:
        if (
            entry.schema_status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED
            and not entry.blocked
            and entry.schema_family != IITPAVE_SCHEMA_FAMILY_UNKNOWN
        ):
            filenames.setdefault(entry.schema_family, []).append(entry.source_filename)

    return tuple(
        IITPaveSchemaFamilyCoverage(
            schema_family=family,
            fixture_count=len(names),
            source_filenames=tuple(sorted(names)),
        )
        for family, names in sorted(filenames.items())
    )


def _status(
    total: int,
    verified: int,
    mapped: int,
    unknown: int,
    blocked: int,
) -> tuple[str, bool]:
    if total == 0:
        return IITPAVE_SCHEMA_MANIFEST_STATUS_NO_FIXTURES, False
    if verified == 0:
        return IITPAVE_SCHEMA_MANIFEST_STATUS_NO_VERIFIED_FIXTURES, False
    if unknown or blocked:
        return IITPAVE_SCHEMA_MANIFEST_STATUS_BLOCKED_UNKNOWN_SCHEMA, False
    if mapped:
        return IITPAVE_SCHEMA_MANIFEST_STATUS_AUDIT_READY, True
    return IITPAVE_SCHEMA_MANIFEST_STATUS_NO_VERIFIED_FIXTURES, False


def _summary(
    *,
    status: str,
    total: int,
    verified: int,
    mapped: int,
    blocked: int,
    unknown: int,
    unsupported: int,
    families: tuple[IITPaveSchemaFamilyCoverage, ...],
) -> tuple[str, ...]:
    family_text = ", ".join(
        f"{item.schema_family}={item.fixture_count}" for item in families
    ) or "none"
    return (
        f"Fixture records scanned: {total}; verified for schema review: {verified}.",
        f"Mapped schema fixtures: {mapped}; blocked schema fixtures: {blocked}; unknown schema fixtures: {unknown}; unsupported fixtures: {unsupported}.",
        f"Schema family coverage: {family_text}.",
        f"Parser audit readiness: {status}; engineering calculations remain blocked.",
    )


def build_iitpave_fixture_schema_manifest(
    fixture_dir: Path | str,
    *,
    manifest_name: str = DEFAULT_FIXTURE_MANIFEST,
) -> IITPaveFixtureSchemaManifest:
    """Build an audit-only schema coverage manifest from IITPAVE fixtures."""
    intake = intake_iitpave_fixture_folder(fixture_dir, manifest_name=manifest_name)
    entries: list[IITPaveFixtureSchemaManifestEntry] = []
    issues: list[IITPaveEnvironmentIssue] = list(intake.issues)

    for record in intake.records:
        if record.verification_status == FIXTURE_STATUS_VERIFIED:
            entry = _entry_for_verified_record(record)
        elif record.contract_status == IITPAVE_OUTPUT_STATUS_UNSUPPORTED:
            entry = _entry_for_unmapped_record(
                record,
                "Fixture output contract is unsupported; schema mapping is blocked.",
            )
        else:
            entry = _entry_for_unmapped_record(
                record,
                "Fixture is not verified_contract_sample; schema mapping is not evaluated.",
            )
        entries.append(entry)
        issues.extend(entry.issues)

    entry_tuple = tuple(entries)
    status_counts = Counter(record.verification_status for record in intake.records)
    mapped = sum(
        1
        for entry in entry_tuple
        if entry.schema_status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED
        and not entry.blocked
    )
    blocked = sum(
        1
        for entry in entry_tuple
        if entry.verification_status == FIXTURE_STATUS_VERIFIED and entry.blocked
    )
    unknown = sum(
        1
        for entry in entry_tuple
        if entry.verification_status == FIXTURE_STATUS_VERIFIED
        and entry.schema_family == IITPAVE_SCHEMA_FAMILY_UNKNOWN
    )
    unsupported = sum(
        1
        for entry in entry_tuple
        if entry.contract_status == IITPAVE_OUTPUT_STATUS_UNSUPPORTED
    )
    verified = status_counts[FIXTURE_STATUS_VERIFIED]
    total = len(intake.records)
    families = _family_coverage(entry_tuple)
    status, audit_ready = _status(
        total=total,
        verified=verified,
        mapped=mapped,
        unknown=unknown,
        blocked=blocked,
    )

    if audit_ready:
        issues.append(_issue(
            VALIDATION_INFO,
            "schema_manifest",
            "Verified fixture schemas are covered for audit reporting; engineering calculations remain blocked.",
        ))
    else:
        issues.append(_issue(
            VALIDATION_WARNING,
            "schema_manifest",
            "Verified fixture schema coverage is incomplete or unavailable; parser use remains blocked.",
        ))

    return IITPaveFixtureSchemaManifest(
        intake=intake,
        status=status,
        parser_audit_ready=audit_ready,
        engineering_calculations_allowed=False,
        entries=entry_tuple,
        family_coverage=families,
        total_fixture_count=total,
        verified_fixture_count=verified,
        mapped_schema_count=mapped,
        blocked_schema_count=blocked,
        unknown_schema_count=unknown,
        unsupported_schema_count=unsupported,
        pending_review_count=status_counts[FIXTURE_STATUS_OPERATOR_PENDING],
        unverified_count=status_counts[FIXTURE_STATUS_UNVERIFIED],
        rejected_count=status_counts[FIXTURE_STATUS_REJECTED],
        audit_summary=_summary(
            status=status,
            total=total,
            verified=verified,
            mapped=mapped,
            blocked=blocked,
            unknown=unknown,
            unsupported=unsupported,
            families=families,
        ),
        issues=tuple(issues),
    )
