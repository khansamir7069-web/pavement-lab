"""Project export/import foundation.

Versioned JSON payloads for backups, project sharing, and future migration
workflows. This layer is intentionally persistence-only: it creates new
projects on import and never changes engineering calculations or UI state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import __app_name__, __product_name__, __version__
from app.core.config_profiles import load_application_config

from .repository import Database
from .schema import (
    Client,
    ConditionSurvey,
    IITPaveSchemaDiagnosticsHistory,
    IITPaveSchemaHistorySelectionAudit,
    MaintenanceDesign,
    MaterialQuantityDesign,
    MechanisticValidation,
    MixDesign,
    Project,
    ReportRevisionSnapshotRecord,
    StructuralDesign,
    StabilizedDesign,
    TrafficAnalysis,
)


PROJECT_EXPORT_FORMAT = "sampave.project_export"
PROJECT_EXPORT_FORMAT_VERSION = "1.0"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ProjectExchangeIssue:
    severity: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ProjectExchangeValidationResult:
    issues: tuple[ProjectExchangeIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.severity == SEVERITY_ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == SEVERITY_WARNING for i in self.issues)


@dataclass(frozen=True, slots=True)
class ProjectImportResult:
    project_id: int
    work_name: str
    issues: tuple[ProjectExchangeIssue, ...] = ()


class ProjectImportError(ValueError):
    """Raised when an import payload is clearly malformed."""

    def __init__(self, result: ProjectExchangeValidationResult):
        self.result = result
        messages = "; ".join(i.message for i in result.issues) or "Invalid project export payload."
        super().__init__(messages)


_PROJECT_FIELDS: tuple[str, ...] = (
    "work_name",
    "work_order_no",
    "work_order_date",
    "agency",
    "submitted_by",
    "mix_type",
    "modules_json",
    "binder_grade",
    "binder_properties_json",
    "status",
)

_CHILD_SECTIONS: dict[str, tuple[type, tuple[str, ...], tuple[str, ...]]] = {
    "mix_designs": (
        MixDesign,
        (
            "gradation_json",
            "spgr_json",
            "gmb_json",
            "gmm_json",
            "stability_flow_json",
            "materials_json",
            "gsb",
            "gb",
            "obc_pct",
            "gmb_at_obc",
            "gmm_at_obc",
            "stability_at_obc_kn",
            "flow_at_obc_mm",
            "vma_at_obc_pct",
            "vfb_at_obc_pct",
            "air_voids_at_obc_pct",
            "compliance_pass",
            "summary_json",
            "computed_at",
        ),
        (
            "gradation_json",
            "spgr_json",
            "gmb_json",
            "gmm_json",
            "stability_flow_json",
            "materials_json",
            "summary_json",
        ),
    ),
    "structural_designs": (
        StructuralDesign,
        (
            "inputs_json",
            "design_msa",
            "growth_factor",
            "subgrade_mr_mpa",
            "total_pavement_thickness_mm",
            "composition_json",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "composition_json"),
    ),
    "maintenance_designs": (
        MaintenanceDesign,
        ("sub_module", "inputs_json", "results_json", "notes", "computed_at"),
        ("inputs_json", "results_json"),
    ),
    "material_quantities": (
        MaterialQuantityDesign,
        (
            "inputs_json",
            "results_json",
            "total_layer_tonnage_t",
            "total_binder_tonnage_t",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "results_json"),
    ),
    "traffic_analyses": (
        TrafficAnalysis,
        (
            "inputs_json",
            "results_json",
            "design_msa",
            "aashto_esal",
            "traffic_category",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "results_json"),
    ),
    "condition_surveys": (
        ConditionSurvey,
        (
            "inputs_json",
            "results_json",
            "pci_score",
            "condition_category",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "results_json"),
    ),
    "stabilized_designs": (
        StabilizedDesign,
        (
            "inputs_json",
            "results_json",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "results_json"),
    ),
    "mechanistic_validations": (
        MechanisticValidation,
        (
            "inputs_json",
            "summary_json",
            "refused",
            "is_placeholder",
            "fatigue_verdict",
            "rutting_verdict",
            "fatigue_life_msa",
            "rutting_life_msa",
            "design_msa",
            "refused_reason",
            "notes",
            "computed_at",
        ),
        ("inputs_json", "summary_json"),
    ),
    "iitpave_schema_diagnostics": (
        IITPaveSchemaDiagnosticsHistory,
        (
            "fixture_dir",
            "report_path",
            "workflow_status",
            "manifest_status",
            "parser_audit_ready",
            "engineering_calculations_allowed",
            "total_fixture_count",
            "verified_fixture_count",
            "mapped_schema_count",
            "blocked_schema_count",
            "unknown_schema_count",
            "unsupported_schema_count",
            "summary_json",
            "operator_message",
            "generated_at",
        ),
        ("summary_json",),
    ),
    "iitpave_schema_history_selection_audits": (
        IITPaveSchemaHistorySelectionAudit,
        (
            "report_path",
            "decision_status",
            "available_history_ids_json",
            "selected_history_ids_json",
            "skipped_unknown_history_ids_json",
            "included_history_count",
            "diagnostic_row_count",
            "engineering_calculations_allowed",
            "summary_json",
            "generated_at",
        ),
        (
            "available_history_ids_json",
            "selected_history_ids_json",
            "skipped_unknown_history_ids_json",
            "summary_json",
        ),
    ),
    "report_revision_snapshots": (
        ReportRevisionSnapshotRecord,
        (
            "report_identifier",
            "revision_label",
            "report_path",
            "provenance_fingerprint",
            "validation_warnings_json",
            "schema_history_selection_json",
            "export_provenance_json",
            "summary_json",
            "engineering_calculations_allowed",
            "generated_at",
        ),
        (
            "validation_warnings_json",
            "schema_history_selection_json",
            "export_provenance_json",
            "summary_json",
        ),
    ),
}


def _utc_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _dt_to_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _json_mapping(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _json_value_for_storage(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value)
    return value


def _serialized_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _dt_to_iso(value)
    return value


def _record_payload(row: Any, fields: Sequence[str]) -> dict[str, Any]:
    payload = {"source_id": getattr(row, "id", None)}
    for field in fields:
        payload[field] = _serialized_value(getattr(row, field))
    return payload


def _issue(severity: str, field: str, message: str) -> ProjectExchangeIssue:
    return ProjectExchangeIssue(severity=severity, field=field, message=message)


def export_project(db: Database, project_id: int) -> dict[str, Any]:
    """Export one project to a versioned JSON-compatible dict."""
    issues: list[ProjectExchangeIssue] = []
    with db.session() as s:
        stmt = (
            select(Project)
            .options(joinedload(Project.client))
            .where(Project.id == project_id)
        )
        project = s.scalars(stmt).first()
        if project is None:
            raise ValueError(f"Project #{project_id} not found.")

        config_payload = _json_mapping(project.config_json)
        if project.config_json and config_payload is None:
            issues.append(_issue(
                SEVERITY_WARNING,
                "project.config_json",
                "Project config_json is malformed; exported resolved fallback metadata only.",
            ))
        resolved_config = db.load_project_config(project_id)

        project_payload: dict[str, Any] = {
            "source_id": project.id,
            "work_name": project.work_name,
            "created_at": _dt_to_iso(project.created_at),
            "updated_at": _dt_to_iso(project.updated_at),
            "config": config_payload,
            "config_resolved": resolved_config.as_dict(),
        }
        for field in _PROJECT_FIELDS:
            project_payload[field] = _serialized_value(getattr(project, field))
        if project.client is not None:
            project_payload["client"] = {
                "name": project.client.name,
                "address": project.client.address or "",
                "contact": project.client.contact or "",
            }

        records: dict[str, list[dict[str, Any]]] = {}
        for section, (model, fields, _json_fields) in _CHILD_SECTIONS.items():
            rows = s.scalars(
                select(model)
                .where(model.project_id == project_id)
                .order_by(model.id)
            ).all()
            records[section] = [_record_payload(row, fields) for row in rows]

    validation = ProjectExchangeValidationResult(tuple(issues))
    return {
        "format": PROJECT_EXPORT_FORMAT,
        "format_version": PROJECT_EXPORT_FORMAT_VERSION,
        "exported_at": _utc_iso(),
        "application": {
            "name": __app_name__,
            "product": __product_name__,
            "version": __version__,
        },
        "project": project_payload,
        "records": records,
        "validation": {
            "ok": validation.ok,
            "issues": [i.as_dict() for i in validation.issues],
        },
    }


def validate_project_export_payload(
    payload: Mapping[str, Any] | None,
) -> ProjectExchangeValidationResult:
    issues: list[ProjectExchangeIssue] = []
    if not isinstance(payload, Mapping):
        return ProjectExchangeValidationResult((
            _issue(SEVERITY_ERROR, "payload", "Project export payload must be a mapping."),
        ))

    if payload.get("format") != PROJECT_EXPORT_FORMAT:
        issues.append(_issue(
            SEVERITY_ERROR,
            "format",
            f"Unsupported project export format {payload.get('format')!r}.",
        ))

    version = payload.get("format_version")
    if version is None:
        issues.append(_issue(
            SEVERITY_WARNING,
            "format_version",
            "Export format version is missing; attempting import as version 1.0.",
        ))
    elif str(version).split(".", 1)[0] != PROJECT_EXPORT_FORMAT_VERSION.split(".", 1)[0]:
        issues.append(_issue(
            SEVERITY_ERROR,
            "format_version",
            f"Unsupported project export major version {version!r}.",
        ))
    elif str(version) != PROJECT_EXPORT_FORMAT_VERSION:
        issues.append(_issue(
            SEVERITY_WARNING,
            "format_version",
            f"Export format version {version!r} differs from supported {PROJECT_EXPORT_FORMAT_VERSION!r}.",
        ))

    project = payload.get("project")
    if not isinstance(project, Mapping):
        issues.append(_issue(SEVERITY_ERROR, "project", "Project block must be a mapping."))
    else:
        work_name = project.get("work_name")
        if not isinstance(work_name, str) or not work_name.strip():
            issues.append(_issue(SEVERITY_ERROR, "project.work_name", "Project work_name is required."))
        config = project.get("config")
        if config is not None and not isinstance(config, Mapping):
            issues.append(_issue(
                SEVERITY_WARNING,
                "project.config",
                "Project config block is not a mapping; default config will be used.",
            ))

    records = payload.get("records", {})
    if records is None:
        records = {}
    if not isinstance(records, Mapping):
        issues.append(_issue(SEVERITY_ERROR, "records", "Records block must be a mapping when present."))
    else:
        for section, value in records.items():
            if section in _CHILD_SECTIONS and not isinstance(value, list):
                issues.append(_issue(
                    SEVERITY_ERROR,
                    f"records.{section}",
                    f"Records section {section!r} must be a list.",
                ))
            elif section not in _CHILD_SECTIONS:
                issues.append(_issue(
                    SEVERITY_WARNING,
                    f"records.{section}",
                    f"Unknown records section {section!r} will be ignored.",
                ))

    return ProjectExchangeValidationResult(tuple(issues))


def _client_id_from_payload(session, client_payload: Any) -> int | None:
    if not isinstance(client_payload, Mapping):
        return None
    name = str(client_payload.get("name") or "").strip()
    if not name:
        return None
    existing = session.scalars(select(Client).where(Client.name == name)).first()
    if existing:
        return existing.id
    client = Client(
        name=name,
        address=str(client_payload.get("address") or ""),
        contact=str(client_payload.get("contact") or ""),
    )
    session.add(client)
    session.flush()
    return client.id


def _record_kwargs(
    record: Mapping[str, Any],
    fields: Sequence[str],
    json_fields: set[str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for field in fields:
        if field not in record:
            continue
        value = record[field]
        if field.endswith("_at"):
            parsed = _parse_dt(value)
            if parsed is not None:
                kwargs[field] = parsed
        elif field in json_fields:
            kwargs[field] = _json_value_for_storage(value)
        else:
            kwargs[field] = value
    return kwargs


def import_project(db: Database, payload: Mapping[str, Any]) -> ProjectImportResult:
    """Import a project export by creating a new project.

    Existing projects are never overwritten. Source row ids in the payload
    are treated as provenance only and are not reused.
    """
    validation = validate_project_export_payload(payload)
    if not validation.ok:
        raise ProjectImportError(validation)

    issues = list(validation.issues)
    project_payload = payload.get("project")
    if not isinstance(project_payload, Mapping):
        raise ProjectImportError(ProjectExchangeValidationResult((
            _issue(SEVERITY_ERROR, "project", "Project block must be a mapping."),
        )))

    records = payload.get("records") or {}
    if not isinstance(records, Mapping):
        records = {}

    with db.session() as s:
        client_id = _client_id_from_payload(s, project_payload.get("client"))
        project_kwargs: dict[str, Any] = {
            field: project_payload.get(field)
            for field in _PROJECT_FIELDS
            if field in project_payload
        }
        project_kwargs["work_name"] = str(project_payload["work_name"]).strip()
        project_kwargs.setdefault("mix_type", "")
        if "modules_json" in project_kwargs:
            project_kwargs["modules_json"] = _json_value_for_storage(project_kwargs["modules_json"])
        if "binder_properties_json" in project_kwargs:
            project_kwargs["binder_properties_json"] = _json_value_for_storage(
                project_kwargs["binder_properties_json"]
            )
        if client_id is not None:
            project_kwargs["client_id"] = client_id

        created_at = _parse_dt(project_payload.get("created_at"))
        updated_at = _parse_dt(project_payload.get("updated_at"))
        if created_at is not None:
            project_kwargs["created_at"] = created_at
        if updated_at is not None:
            project_kwargs["updated_at"] = updated_at

        project = Project(**project_kwargs)
        s.add(project)
        s.flush()

        config_payload = project_payload.get("config")
        if isinstance(config_payload, Mapping):
            # Validate through the central profile loader before preserving.
            cfg = load_application_config(config_payload, source=f"import:{project.id}")
            if cfg.metadata.validation_issues:
                issues.extend(
                    ProjectExchangeIssue(
                        severity=SEVERITY_WARNING,
                        field=f"project.config.{issue.field}",
                        message=issue.message,
                    )
                    for issue in cfg.metadata.validation_issues
                )
            project.config_json = json.dumps(dict(config_payload), sort_keys=True)
        elif config_payload is not None:
            cfg = load_application_config("malformed-import-config", source=f"import:{project.id}")
            issues.extend(
                ProjectExchangeIssue(
                    severity=SEVERITY_WARNING,
                    field=f"project.config.{issue.field}",
                    message=issue.message,
                )
                for issue in cfg.metadata.validation_issues
            )

        for section, (model, fields, json_fields) in _CHILD_SECTIONS.items():
            raw_records = records.get(section) or []
            for idx, record in enumerate(raw_records):
                if not isinstance(record, Mapping):
                    issues.append(_issue(
                        SEVERITY_WARNING,
                        f"records.{section}[{idx}]",
                        "Record is not a mapping and was skipped.",
                    ))
                    continue
                kwargs = _record_kwargs(record, fields, set(json_fields))
                row = model(project_id=project.id, **kwargs)
                s.add(row)

        s.flush()
        project_id = project.id
        work_name = project.work_name

    return ProjectImportResult(
        project_id=project_id,
        work_name=work_name,
        issues=tuple(issues),
    )


def write_project_export(payload: Mapping[str, Any], path: Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out


def read_project_export(path: Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ProjectImportError(ProjectExchangeValidationResult((
            _issue(SEVERITY_ERROR, "payload", "Project export file must contain a JSON object."),
        )))
    return parsed
