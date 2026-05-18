"""Operator workflow for IITPAVE fixture-folder schema diagnostics.

Phase 32 provides a guarded entry point for selecting a local fixture folder
and producing audit diagnostics. It does not parse engineering values, run
mechanistic checks, or enable compliance conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import (
    DEFAULT_FIXTURE_MANIFEST,
    IITPaveFixtureSchemaManifest,
    build_iitpave_fixture_schema_manifest,
)
from app.core.config_profiles import (
    VALIDATION_INFO,
    VALIDATION_WARNING,
)
from app.core.iitpave.discovery import IITPaveEnvironmentIssue

from .iitpave_schema_report import (
    IITPaveSchemaReportContext,
    IITPaveSchemaReportSummary,
    build_iitpave_schema_manifest_docx,
    build_iitpave_schema_report_summary,
)


IITPAVE_SCHEMA_WORKFLOW_STATUS_SUMMARY_ONLY = "summary_generated"
IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN = "report_written"
IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_BLOCKED = "report_write_blocked"


@dataclass(frozen=True, slots=True)
class IITPaveSchemaDiagnosticsWorkflowResult:
    fixture_dir: str
    manifest: IITPaveFixtureSchemaManifest
    report_summary: IITPaveSchemaReportSummary
    status: str
    report_path: str = ""
    report_written: bool = False
    engineering_calculations_allowed: bool = False
    operator_message: str = ""
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (
            IITPAVE_SCHEMA_WORKFLOW_STATUS_SUMMARY_ONLY,
            IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "fixture_dir": self.fixture_dir,
            "report_path": self.report_path,
            "report_written": self.report_written,
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "operator_message": self.operator_message,
            "manifest": self.manifest.as_dict(),
            "report_summary": self.report_summary.as_dict(),
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _operator_message(
    summary: IITPaveSchemaReportSummary,
    *,
    report_path: Path | None = None,
) -> str:
    lines = [
        summary.parser_readiness,
        *summary.operator_summary,
    ]
    if report_path is not None:
        lines.append(f"Schema diagnostics report written: {report_path}")
    lines.append("Engineering calculations remain blocked.")
    return "\n".join(lines)


def run_iitpave_schema_diagnostics_workflow(
    fixture_dir: Path | str,
    *,
    report_path: Path | str | None = None,
    context: IITPaveSchemaReportContext | None = None,
    manifest_name: str = DEFAULT_FIXTURE_MANIFEST,
) -> IITPaveSchemaDiagnosticsWorkflowResult:
    """Build schema diagnostics from a local fixture folder, optionally as docx."""
    fixture_root = Path(fixture_dir)
    manifest = build_iitpave_fixture_schema_manifest(
        fixture_root,
        manifest_name=manifest_name,
    )
    summary = build_iitpave_schema_report_summary(manifest)
    issues: list[IITPaveEnvironmentIssue] = list(manifest.issues)

    if report_path is None:
        issues.append(_issue(
            VALIDATION_INFO,
            "schema_workflow.report",
            "Schema diagnostics summary generated without writing a report file.",
        ))
        return IITPaveSchemaDiagnosticsWorkflowResult(
            fixture_dir=str(fixture_root),
            manifest=manifest,
            report_summary=summary,
            status=IITPAVE_SCHEMA_WORKFLOW_STATUS_SUMMARY_ONLY,
            engineering_calculations_allowed=False,
            operator_message=_operator_message(summary),
            issues=tuple(issues),
        )

    out_path = Path(report_path)
    if out_path.suffix.lower() != ".docx":
        reason = "IITPAVE schema diagnostics report path must end with .docx."
        issues.append(_issue(VALIDATION_WARNING, "schema_workflow.report_path", reason))
        return IITPaveSchemaDiagnosticsWorkflowResult(
            fixture_dir=str(fixture_root),
            manifest=manifest,
            report_summary=summary,
            status=IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_BLOCKED,
            report_path=str(out_path),
            report_written=False,
            engineering_calculations_allowed=False,
            operator_message=f"{reason}\nEngineering calculations remain blocked.",
            issues=tuple(issues),
        )

    build_iitpave_schema_manifest_docx(
        out_path,
        context or IITPaveSchemaReportContext(),
        manifest,
    )
    issues.append(_issue(
        VALIDATION_INFO,
        "schema_workflow.report",
        f"Schema diagnostics report written: {out_path}",
    ))
    return IITPaveSchemaDiagnosticsWorkflowResult(
        fixture_dir=str(fixture_root),
        manifest=manifest,
        report_summary=summary,
        status=IITPAVE_SCHEMA_WORKFLOW_STATUS_REPORT_WRITTEN,
        report_path=str(out_path),
        report_written=True,
        engineering_calculations_allowed=False,
        operator_message=_operator_message(summary, report_path=out_path),
        issues=tuple(issues),
    )
