"""Guarded IITPAVE verified-fixture schema mapping layer.

Phases 28-29 map only reviewed fixture structure exposed by the conservative
parser-contract layer. They do not extract strains, stresses, layer values,
fatigue life, rutting life, or IRC compliance conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
)

from .discovery import IITPaveEnvironmentIssue
from .fixture_intake import IITPaveFixtureRecord
from .parser_contract import (
    IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED,
    IITPAVE_SECTION_HEADER,
    IITPAVE_SECTION_LABELED_BLOCK,
    IITPAVE_SECTION_TABLE_LIKE,
    IITPaveParserContractSection,
    IITPaveVerifiedParserContractResult,
    inspect_iitpave_verified_parser_contract,
)


IITPAVE_SCHEMA_MAPPING_STATUS_BLOCKED = "blocked_schema_mapping"
IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN = "unknown_schema"
IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED = "schema_mapped"

IITPAVE_SCHEMA_SECTION_OUTPUT_HEADER = "output_header"
IITPAVE_SCHEMA_SECTION_CONTEXT_BLOCK = "recognized_context_block"
IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_CONTEXT = "stress_strain_context"
IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE = (
    "stress_strain_table_candidate"
)

IITPAVE_SCHEMA_FAMILY_UNKNOWN = "unknown_schema_family"
IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE = "direct_stress_strain_table"
IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE = (
    "elastic_layer_stress_strain_table"
)

_STRESS_STRAIN_MARKERS = ("stress", "strain")
_ELASTIC_LAYER_MARKERS = ("elastic layer", "elastic-layer", "elastic layered")
_MAX_CONTEXT_TABLE_LINE_GAP = 8


@dataclass(frozen=True, slots=True)
class IITPaveSchemaSectionMapping:
    schema_role: str
    section_type: str
    source_label: str
    start_line_index: int
    end_line_index: int
    marker: str = ""
    values_extracted: bool = False
    source_section: IITPaveParserContractSection | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_role": self.schema_role,
            "section_type": self.section_type,
            "source_label": self.source_label,
            "start_line_index": self.start_line_index,
            "end_line_index": self.end_line_index,
            "marker": self.marker,
            "values_extracted": self.values_extracted,
            "source_section": (
                self.source_section.as_dict() if self.source_section else None
            ),
        }


@dataclass(frozen=True, slots=True)
class IITPaveVerifiedFixtureSchemaMappingResult:
    parser_contract: IITPaveVerifiedParserContractResult
    status: str
    blocked: bool
    blocked_reason: str = ""
    schema_family: str = IITPAVE_SCHEMA_FAMILY_UNKNOWN
    classification_markers: tuple[str, ...] = ()
    mappings: tuple[IITPaveSchemaSectionMapping, ...] = ()
    engineering_values_extracted: bool = False
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and self.status == IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "schema_family": self.schema_family,
            "classification_markers": list(self.classification_markers),
            "mapping_count": len(self.mappings),
            "engineering_values_extracted": self.engineering_values_extracted,
            "parser_contract": self.parser_contract.as_dict(),
            "mappings": [m.as_dict() for m in self.mappings],
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _blocked(
    parser_contract: IITPaveVerifiedParserContractResult,
    *,
    status: str,
    reason: str,
    issues: list[IITPaveEnvironmentIssue],
    schema_family: str = IITPAVE_SCHEMA_FAMILY_UNKNOWN,
    classification_markers: tuple[str, ...] = (),
    mappings: tuple[IITPaveSchemaSectionMapping, ...] = (),
) -> IITPaveVerifiedFixtureSchemaMappingResult:
    issues.append(_issue(VALIDATION_ERROR, "schema_mapping", reason))
    return IITPaveVerifiedFixtureSchemaMappingResult(
        parser_contract=parser_contract,
        status=status,
        blocked=True,
        blocked_reason=reason,
        schema_family=schema_family,
        classification_markers=classification_markers,
        mappings=mappings,
        engineering_values_extracted=False,
        issues=tuple(issues),
    )


def _mapping(
    section: IITPaveParserContractSection,
    schema_role: str,
) -> IITPaveSchemaSectionMapping:
    return IITPaveSchemaSectionMapping(
        schema_role=schema_role,
        section_type=section.section_type,
        source_label=section.label,
        start_line_index=section.start_line_index,
        end_line_index=section.end_line_index,
        marker=section.marker,
        values_extracted=False,
        source_section=section,
    )


def _section_text(section: IITPaveParserContractSection) -> str:
    return " ".join((
        section.marker,
        section.label,
        *section.evidence_preview,
    )).lower()


def _is_stress_strain_context(section: IITPaveParserContractSection) -> bool:
    text = _section_text(section)
    return any(m in text for m in _STRESS_STRAIN_MARKERS)


def _nearest_prior_stress_strain_context(
    table: IITPaveParserContractSection,
    contexts: tuple[IITPaveParserContractSection, ...],
) -> IITPaveParserContractSection | None:
    candidates = tuple(
        c for c in contexts
        if c.end_line_index <= table.start_line_index
        and table.start_line_index - c.end_line_index <= _MAX_CONTEXT_TABLE_LINE_GAP
    )
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.end_line_index)


def _classification_markers(
    mappings: tuple[IITPaveSchemaSectionMapping, ...],
) -> tuple[str, ...]:
    text = " ".join(
        _section_text(m.source_section) if m.source_section else m.source_label.lower()
        for m in mappings
    )
    markers: list[str] = []
    if any(marker in text for marker in _ELASTIC_LAYER_MARKERS):
        markers.append("elastic_layer_context")
    if "stress" in text:
        markers.append("stress_context")
    if "strain" in text:
        markers.append("strain_context")
    if any(
        m.schema_role == IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE
        for m in mappings
    ):
        markers.append("table_candidate")
    return tuple(markers)


def _schema_family(
    mappings: tuple[IITPaveSchemaSectionMapping, ...],
) -> tuple[str, tuple[str, ...]]:
    markers = _classification_markers(mappings)
    marker_set = set(markers)
    if "table_candidate" not in marker_set or "strain_context" not in marker_set:
        return IITPAVE_SCHEMA_FAMILY_UNKNOWN, markers
    if "elastic_layer_context" in marker_set:
        return IITPAVE_SCHEMA_FAMILY_ELASTIC_LAYER_STRESS_STRAIN_TABLE, markers
    return IITPAVE_SCHEMA_FAMILY_DIRECT_STRESS_STRAIN_TABLE, markers


def _schema_mappings(
    sections: tuple[IITPaveParserContractSection, ...],
) -> tuple[IITPaveSchemaSectionMapping, ...]:
    mappings: list[IITPaveSchemaSectionMapping] = []
    stress_strain_contexts = tuple(
        section
        for section in sections
        if section.section_type == IITPAVE_SECTION_LABELED_BLOCK
        and _is_stress_strain_context(section)
    )

    for section in sections:
        if section.section_type == IITPAVE_SECTION_HEADER:
            mappings.append(_mapping(section, IITPAVE_SCHEMA_SECTION_OUTPUT_HEADER))
        elif section.section_type == IITPAVE_SECTION_LABELED_BLOCK:
            role = (
                IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_CONTEXT
                if _is_stress_strain_context(section)
                else IITPAVE_SCHEMA_SECTION_CONTEXT_BLOCK
            )
            mappings.append(_mapping(section, role))
        elif (
            section.section_type == IITPAVE_SECTION_TABLE_LIKE
            and _nearest_prior_stress_strain_context(section, stress_strain_contexts)
            is not None
        ):
            mappings.append(
                _mapping(section, IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE)
            )

    return tuple(mappings)


def map_iitpave_verified_fixture_schema(
    record: IITPaveFixtureRecord,
    *,
    text: str | None = None,
) -> IITPaveVerifiedFixtureSchemaMappingResult:
    """Map reviewed IITPAVE fixture sections without parsing engineering values."""
    parser_contract = inspect_iitpave_verified_parser_contract(record, text=text)
    issues: list[IITPaveEnvironmentIssue] = list(parser_contract.issues)

    if parser_contract.blocked:
        reason = (
            "IITPAVE verified-fixture schema mapping requires an unblocked "
            "parser-contract inspection."
        )
        return _blocked(
            parser_contract,
            status=IITPAVE_SCHEMA_MAPPING_STATUS_BLOCKED,
            reason=reason,
            issues=issues,
        )

    if parser_contract.status != IITPAVE_PARSER_CONTRACT_STATUS_SECTIONS_DETECTED:
        reason = (
            "IITPAVE fixture schema is not recognized completely enough for "
            "mapping; parsing remains blocked."
        )
        return _blocked(
            parser_contract,
            status=IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN,
            reason=reason,
            issues=issues,
        )

    mappings = _schema_mappings(parser_contract.sections)
    schema_family, classification_markers = _schema_family(mappings)
    roles = {m.schema_role for m in mappings}
    required_roles = {
        IITPAVE_SCHEMA_SECTION_OUTPUT_HEADER,
        IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_CONTEXT,
        IITPAVE_SCHEMA_SECTION_STRESS_STRAIN_TABLE_CANDIDATE,
    }
    missing = sorted(required_roles - roles)
    if missing:
        reason = (
            "IITPAVE fixture schema mapping is incomplete; missing reviewed "
            f"schema roles: {', '.join(missing)}."
        )
        return _blocked(
            parser_contract,
            status=IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN,
            reason=reason,
            issues=issues,
            schema_family=schema_family,
            classification_markers=classification_markers,
            mappings=mappings,
        )
    if schema_family == IITPAVE_SCHEMA_FAMILY_UNKNOWN:
        reason = (
            "IITPAVE fixture schema mapping is recognized structurally, but no "
            "reviewed schema family could be classified safely."
        )
        return _blocked(
            parser_contract,
            status=IITPAVE_SCHEMA_MAPPING_STATUS_UNKNOWN,
            reason=reason,
            issues=issues,
            schema_family=schema_family,
            classification_markers=classification_markers,
            mappings=mappings,
        )

    issues.append(_issue(
        VALIDATION_INFO,
        "schema_mapping",
        "Verified fixture schema sections were classified; engineering parsing remains disabled.",
    ))
    return IITPaveVerifiedFixtureSchemaMappingResult(
        parser_contract=parser_contract,
        status=IITPAVE_SCHEMA_MAPPING_STATUS_MAPPED,
        blocked=False,
        schema_family=schema_family,
        classification_markers=classification_markers,
        mappings=mappings,
        engineering_values_extracted=False,
        issues=tuple(issues),
    )
