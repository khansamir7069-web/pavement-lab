"""IITPAVE output contract detection and parser guardrails.

Phase 25 inspects raw output text/files only. It does not run IITPAVE,
generate pavement input, parse engineering output, calculate strains, or
make IRC:37 compliance claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)

from .discovery import IITPaveEnvironmentIssue
from .runner import SOURCE_EXTERNAL, SOURCE_STUB, STUB_OUTPUT_VERSION


IITPAVE_OUTPUT_STATUS_MISSING = "missing"
IITPAVE_OUTPUT_STATUS_UNREADABLE = "unreadable"
IITPAVE_OUTPUT_STATUS_EMPTY = "empty"
IITPAVE_OUTPUT_STATUS_STUB_CONTRACT = "stub_contract"
IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_SUPPORTED = "real_contract_supported"
IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING = "real_contract_pending"
IITPAVE_OUTPUT_STATUS_UNSUPPORTED = "unsupported"

IITPAVE_OUTPUT_FORMAT_STUB = "roadx_iitpave_stub"
IITPAVE_OUTPUT_FORMAT_REAL_TABLE = "real_iitpave_stress_strain_table"
IITPAVE_OUTPUT_FORMAT_REAL_PENDING = "real_iitpave_pending"
IITPAVE_OUTPUT_FORMAT_UNKNOWN = "unknown"

_REAL_IITPAVE_HINTS = (
    "iitpave",
    "iit pave",
    "irc:37",
    "irc 37",
    "elastic layer",
    "stress",
    "strain",
)

_SUPPORTED_TABLE_MARKERS = ("sigmaz", "sigmat", "sigmar", "epz", "ept", "epr")


@dataclass(frozen=True, slots=True)
class IITPaveOutputContractResult:
    """Audit-friendly output contract classification."""
    status: str
    format_key: str
    parse_allowed: bool
    parser_source: str = ""
    source_path: str = ""
    byte_count: int = 0
    char_count: int = 0
    line_count: int = 0
    markers: tuple[str, ...] = ()
    blocked_reason: str = ""
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.parse_allowed and not any(
            i.severity == VALIDATION_ERROR for i in self.issues
        )

    @property
    def blocked(self) -> bool:
        return not self.parse_allowed

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == VALIDATION_WARNING for i in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "status": self.status,
            "format_key": self.format_key,
            "parse_allowed": self.parse_allowed,
            "parser_source": self.parser_source,
            "source_path": self.source_path,
            "byte_count": self.byte_count,
            "char_count": self.char_count,
            "line_count": self.line_count,
            "markers": list(self.markers),
            "blocked_reason": self.blocked_reason,
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _line_count(text: str) -> int:
    return len(text.splitlines())


def _has_supported_real_table(text: str) -> bool:
    lower = text.lower()
    compact = "".join(ch for ch in lower if ch.isalnum() or ch.isspace())
    compact_markers = set(compact.split())
    if not all(marker in compact_markers or marker in lower for marker in _SUPPORTED_TABLE_MARKERS):
        return False
    return any(char.isdigit() for char in text)


def _result(
    *,
    status: str,
    format_key: str,
    parse_allowed: bool,
    parser_source: str = "",
    source_path: str = "",
    text: str = "",
    byte_count: int | None = None,
    markers: tuple[str, ...] = (),
    blocked_reason: str = "",
    issues: list[IITPaveEnvironmentIssue] | None = None,
) -> IITPaveOutputContractResult:
    return IITPaveOutputContractResult(
        status=status,
        format_key=format_key,
        parse_allowed=parse_allowed,
        parser_source=parser_source,
        source_path=source_path,
        byte_count=len(text.encode("utf-8")) if byte_count is None else byte_count,
        char_count=len(text),
        line_count=_line_count(text),
        markers=markers,
        blocked_reason=blocked_reason,
        issues=tuple(issues or ()),
    )


def _detect_text_contract(
    text: str,
    *,
    source_path: str = "",
    byte_count: int | None = None,
) -> IITPaveOutputContractResult:
    issues: list[IITPaveEnvironmentIssue] = []
    stripped = text.strip()
    if not stripped:
        reason = "IITPAVE output is empty; parsing is blocked."
        issues.append(_issue(VALIDATION_ERROR, "output", reason))
        return _result(
            status=IITPAVE_OUTPUT_STATUS_EMPTY,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            text=text,
            byte_count=byte_count,
            blocked_reason=reason,
            issues=issues,
        )

    markers: list[str] = []
    if STUB_OUTPUT_VERSION in text:
        markers.append(STUB_OUTPUT_VERSION)
    if "pavement_lab iitpave stub output" in text.lower():
        markers.append("pavement_lab iitpave stub output")

    if STUB_OUTPUT_VERSION in markers:
        issues.append(_issue(
            VALIDATION_INFO,
            "output.contract",
            "Recognized RoadX IITPAVE stub output contract; parser may run as placeholder-only.",
        ))
        return _result(
            status=IITPAVE_OUTPUT_STATUS_STUB_CONTRACT,
            format_key=IITPAVE_OUTPUT_FORMAT_STUB,
            parse_allowed=True,
            parser_source=SOURCE_STUB,
            source_path=source_path,
            text=text,
            byte_count=byte_count,
            markers=tuple(markers),
            issues=issues,
        )

    if _has_supported_real_table(text):
        markers.extend(m for m in _SUPPORTED_TABLE_MARKERS if m not in markers)
        issues.append(_issue(
            VALIDATION_INFO,
            "output.contract",
            "Recognized IITPAVE stress/strain table fields; external parser may run.",
        ))
        return _result(
            status=IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_SUPPORTED,
            format_key=IITPAVE_OUTPUT_FORMAT_REAL_TABLE,
            parse_allowed=True,
            parser_source=SOURCE_EXTERNAL,
            source_path=source_path,
            text=text,
            byte_count=byte_count,
            markers=tuple(markers),
            issues=issues,
        )

    lower = text.lower()
    real_hints = tuple(h for h in _REAL_IITPAVE_HINTS if h in lower)
    if real_hints:
        reason = (
            "Raw output contains IITPAVE-like markers, but no verified real "
            "IITPAVE output contract exists in this repository yet; parsing is blocked."
        )
        issues.append(_issue(VALIDATION_WARNING, "output.markers", reason))
        return _result(
            status=IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
            format_key=IITPAVE_OUTPUT_FORMAT_REAL_PENDING,
            parse_allowed=False,
            source_path=source_path,
            text=text,
            byte_count=byte_count,
            markers=real_hints,
            blocked_reason=reason,
            issues=issues,
        )

    reason = "IITPAVE output format is unknown or unsupported; parsing is blocked."
    issues.append(_issue(VALIDATION_ERROR, "output.contract", reason))
    return _result(
        status=IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
        format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
        parse_allowed=False,
        source_path=source_path,
        text=text,
        byte_count=byte_count,
        blocked_reason=reason,
        issues=issues,
    )


def inspect_iitpave_output_contract(
    *,
    text: str | None = None,
    path: Path | str | None = None,
    encoding: str = "utf-8",
) -> IITPaveOutputContractResult:
    """Classify raw IITPAVE output text or file before any parser is used."""
    if text is not None:
        return _detect_text_contract(text, source_path=str(path or ""))

    if path is None:
        reason = "No IITPAVE output text or file path was supplied; parsing is blocked."
        return _result(
            status=IITPAVE_OUTPUT_STATUS_MISSING,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output", reason)],
        )

    out_path = Path(path)
    source_path = str(out_path)
    if "\0" in source_path:
        reason = "IITPAVE output path is invalid or inaccessible: embedded null byte."
        return _result(
            status=IITPAVE_OUTPUT_STATUS_UNREADABLE,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output.path", reason)],
        )
    if not out_path.exists():
        reason = f"IITPAVE output file does not exist: {out_path}"
        return _result(
            status=IITPAVE_OUTPUT_STATUS_MISSING,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output.path", reason)],
        )
    if not out_path.is_file():
        reason = f"IITPAVE output path is not a file: {out_path}"
        return _result(
            status=IITPAVE_OUTPUT_STATUS_UNREADABLE,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output.path", reason)],
        )

    try:
        raw = out_path.read_bytes()
    except OSError as e:
        reason = f"IITPAVE output file is not readable: {out_path} ({e})"
        return _result(
            status=IITPAVE_OUTPUT_STATUS_UNREADABLE,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output.path", reason)],
        )
    if not raw:
        reason = f"IITPAVE output file is empty: {out_path}"
        return _result(
            status=IITPAVE_OUTPUT_STATUS_EMPTY,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            byte_count=0,
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output", reason)],
        )
    try:
        decoded = raw.decode(encoding)
    except UnicodeDecodeError as e:
        reason = f"IITPAVE output file could not be decoded as {encoding}: {e}"
        return _result(
            status=IITPAVE_OUTPUT_STATUS_UNREADABLE,
            format_key=IITPAVE_OUTPUT_FORMAT_UNKNOWN,
            parse_allowed=False,
            source_path=source_path,
            byte_count=len(raw),
            blocked_reason=reason,
            issues=[_issue(VALIDATION_ERROR, "output.encoding", reason)],
        )

    return _detect_text_contract(
        decoded,
        source_path=source_path,
        byte_count=len(raw),
    )
