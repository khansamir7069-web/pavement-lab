"""Conservative IITPAVE verified-output parser contract layer.

Phase 27 recognizes coarse structural sections in verified operator fixtures
only. It does not parse engineering values, compute strains, calculate fatigue
or rutting life, recommend layers, or make IRC:37 compliance claims.
"""
from __future__ import annotations

import re
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
    FIXTURE_STATUS_VERIFIED,
    IITPaveFixtureRecord,
)
from .output_contract import (
    IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
    IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
)


IITPAVE_PARSER_CONTRACT_STATUS_BLOCKED = "blocked_parse"
IITPAVE_PARSER_CONTRACT_STATUS_UNSUPPORTED = "unsupported_contract"
IITPAVE_PARSER_CONTRACT_STATUS_INCOMPLETE = "incomplete_contract"
IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL = "partial_contract"
IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED = "sections_detected"

IITPAVE_SECTION_HEADER = "header_region"
IITPAVE_SECTION_TABLE_LIKE = "table_like_region"
IITPAVE_SECTION_LABELED_BLOCK = "recognized_labeled_block"

_NUMERIC_TOKEN_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
_LABEL_MARKERS = (
    "iitpave",
    "iit pave",
    "irc:37",
    "irc 37",
    "elastic layer",
    "stress",
    "strain",
)


@dataclass(frozen=True, slots=True)
class IITPaveParserContractMarker:
    name: str
    line_indexes: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "line_indexes": list(self.line_indexes),
        }


@dataclass(frozen=True, slots=True)
class IITPaveParserContractSection:
    section_type: str
    label: str
    start_line_index: int
    end_line_index: int
    marker: str = ""
    line_count: int = 0
    evidence_preview: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "section_type": self.section_type,
            "label": self.label,
            "start_line_index": self.start_line_index,
            "end_line_index": self.end_line_index,
            "marker": self.marker,
            "line_count": self.line_count,
            "evidence_preview": list(self.evidence_preview),
        }


@dataclass(frozen=True, slots=True)
class IITPaveVerifiedParserContractResult:
    fixture: IITPaveFixtureRecord
    status: str
    blocked: bool
    blocked_reason: str = ""
    sections: tuple[IITPaveParserContractSection, ...] = ()
    markers: tuple[IITPaveParserContractMarker, ...] = ()
    engineering_values_extracted: bool = False
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and not any(
            i.severity == VALIDATION_ERROR for i in self.issues
        )

    @property
    def partial(self) -> bool:
        return self.status == IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == VALIDATION_WARNING for i in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "section_count": len(self.sections),
            "marker_count": len(self.markers),
            "engineering_values_extracted": self.engineering_values_extracted,
            "fixture": self.fixture.as_dict(),
            "sections": [s.as_dict() for s in self.sections],
            "markers": [m.as_dict() for m in self.markers],
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _blocked(
    record: IITPaveFixtureRecord,
    *,
    status: str,
    reason: str,
    issues: list[IITPaveEnvironmentIssue],
    markers: tuple[IITPaveParserContractMarker, ...] = (),
    sections: tuple[IITPaveParserContractSection, ...] = (),
) -> IITPaveVerifiedParserContractResult:
    issues.append(_issue(VALIDATION_ERROR, "parser_contract", reason))
    return IITPaveVerifiedParserContractResult(
        fixture=record,
        status=status,
        blocked=True,
        blocked_reason=reason,
        sections=sections,
        markers=markers,
        issues=tuple(issues),
    )


def _line_preview(lines: list[str], start: int, end: int) -> tuple[str, ...]:
    return tuple(line[:160] for line in lines[start:end + 1])


def _marker_locations(
    lines: list[str],
    marker_names: tuple[str, ...],
) -> tuple[IITPaveParserContractMarker, ...]:
    markers: list[IITPaveParserContractMarker] = []
    for marker in marker_names:
        lower_marker = marker.lower()
        indexes = tuple(
            idx for idx, line in enumerate(lines) if lower_marker in line.lower()
        )
        if indexes:
            markers.append(IITPaveParserContractMarker(name=marker, line_indexes=indexes))
    return tuple(markers)


def _header_section(lines: list[str]) -> IITPaveParserContractSection | None:
    non_empty = [idx for idx, line in enumerate(lines) if line.strip()]
    if not non_empty:
        return None
    start = non_empty[0]
    end = min(non_empty[-1], start + 4)
    return IITPaveParserContractSection(
        section_type=IITPAVE_SECTION_HEADER,
        label="leading non-empty output region",
        start_line_index=start,
        end_line_index=end,
        line_count=end - start + 1,
        evidence_preview=_line_preview(lines, start, end),
    )


def _is_table_like(line: str) -> bool:
    if not line.strip():
        return False
    tokens = _NUMERIC_TOKEN_RE.findall(line)
    return len(tokens) >= 2


def _table_like_sections(lines: list[str]) -> tuple[IITPaveParserContractSection, ...]:
    sections: list[IITPaveParserContractSection] = []
    start: int | None = None
    for idx, line in enumerate(lines):
        if _is_table_like(line):
            if start is None:
                start = idx
        elif start is not None:
            end = idx - 1
            sections.append(IITPaveParserContractSection(
                section_type=IITPAVE_SECTION_TABLE_LIKE,
                label="numeric table-like line range",
                start_line_index=start,
                end_line_index=end,
                line_count=end - start + 1,
                evidence_preview=_line_preview(lines, start, end),
            ))
            start = None
    if start is not None:
        end = len(lines) - 1
        sections.append(IITPaveParserContractSection(
            section_type=IITPAVE_SECTION_TABLE_LIKE,
            label="numeric table-like line range",
            start_line_index=start,
            end_line_index=end,
            line_count=end - start + 1,
            evidence_preview=_line_preview(lines, start, end),
        ))
    return tuple(sections)


def _labeled_block_sections(lines: list[str]) -> tuple[IITPaveParserContractSection, ...]:
    sections: list[IITPaveParserContractSection] = []
    seen: set[tuple[str, int]] = set()
    for idx, line in enumerate(lines):
        lower = line.lower()
        for marker in _LABEL_MARKERS:
            if marker not in lower:
                continue
            start = idx
            end = idx
            while end + 1 < len(lines) and lines[end + 1].strip() and not _is_table_like(lines[end + 1]):
                end += 1
            key = (marker, start)
            if key in seen:
                continue
            seen.add(key)
            sections.append(IITPaveParserContractSection(
                section_type=IITPAVE_SECTION_LABELED_BLOCK,
                label=f"recognized marker block: {marker}",
                start_line_index=start,
                end_line_index=end,
                marker=marker,
                line_count=end - start + 1,
                evidence_preview=_line_preview(lines, start, end),
            ))
            break
    return tuple(sections)


def inspect_iitpave_verified_parser_contract(
    record: IITPaveFixtureRecord,
    *,
    text: str | None = None,
) -> IITPaveVerifiedParserContractResult:
    """Expose conservative section metadata from one verified fixture record."""
    issues: list[IITPaveEnvironmentIssue] = list(record.issues)

    if record.contract_status == IITPAVE_OUTPUT_STATUS_UNSUPPORTED:
        reason = "IITPAVE fixture contract is unsupported; section inspection is blocked."
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_UNSUPPORTED,
            reason=reason,
            issues=issues,
        )

    if record.verification_status != FIXTURE_STATUS_VERIFIED:
        reason = (
            "IITPAVE parser-contract inspection requires a verified_contract_sample; "
            f"got {record.verification_status!r}."
        )
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_BLOCKED,
            reason=reason,
            issues=issues,
        )

    if record.contract_status != IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING:
        reason = (
            "IITPAVE parser-contract inspection only accepts verified real-output "
            f"pending fixtures; got {record.contract_status!r}."
        )
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_UNSUPPORTED,
            reason=reason,
            issues=issues,
        )

    if not record.detected_markers:
        reason = "Verified fixture has no recognized IITPAVE-like markers; inspection is blocked."
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_INCOMPLETE,
            reason=reason,
            issues=issues,
        )

    if text is None:
        try:
            text = Path(record.source_path).read_text(encoding="utf-8")
        except OSError as e:
            reason = f"Verified fixture text could not be read for section inspection: {e}"
            return _blocked(
                record,
                status=IITPAVE_PARSER_CONTRACT_STATUS_BLOCKED,
                reason=reason,
                issues=issues,
            )

    lines = text.splitlines()
    markers = _marker_locations(lines, record.detected_markers)
    if not markers:
        reason = "Detected markers from intake metadata were not located in fixture text."
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_INCOMPLETE,
            reason=reason,
            issues=issues,
        )

    sections: list[IITPaveParserContractSection] = []
    header = _header_section(lines)
    if header is not None:
        sections.append(header)
    sections.extend(_labeled_block_sections(lines))
    sections.extend(_table_like_sections(lines))

    if not sections:
        reason = "No conservative structural sections were detected in verified fixture."
        return _blocked(
            record,
            status=IITPAVE_PARSER_CONTRACT_STATUS_INCOMPLETE,
            reason=reason,
            issues=issues,
            markers=markers,
        )

    section_types = {section.section_type for section in sections}
    if IITPAVE_SECTION_TABLE_LIKE not in section_types:
        status = IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL
        issues.append(_issue(
            VALIDATION_WARNING,
            "parser_contract.sections",
            "Verified fixture has markers and headers, but no table-like region was detected.",
        ))
    elif IITPAVE_SECTION_LABELED_BLOCK not in section_types:
        status = IITPAVE_PARSER_CONTRACT_STATUS_PARTIAL
        issues.append(_issue(
            VALIDATION_WARNING,
            "parser_contract.sections",
            "Verified fixture has table-like regions, but no recognized labeled block was detected.",
        ))
    else:
        status = IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED
        issues.append(_issue(
            VALIDATION_INFO,
            "parser_contract.sections",
            "Conservative section metadata was detected; engineering value extraction remains disabled.",
        ))

    return IITPaveVerifiedParserContractResult(
        fixture=record,
        status=status,
        blocked=False,
        sections=tuple(sections),
        markers=markers,
        engineering_values_extracted=False,
        issues=tuple(issues),
    )
