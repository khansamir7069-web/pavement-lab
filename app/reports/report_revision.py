"""Audit-only report revision snapshot models.

Phase 40 stores compact report-generation snapshots for traceability and
future comparison workflows. It deliberately does not implement a diff engine
or enable any engineering calculations.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence


REPORT_REVISION_HISTORY_STATUS_EMPTY = "report_revision_history_empty"
REPORT_REVISION_HISTORY_STATUS_AVAILABLE = "report_revision_history_available"


def _payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    return str(value or "")


def _ids_payload(raw: Any) -> tuple[int, ...]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return ()
    if not isinstance(raw, SequenceABC) or isinstance(raw, (bytes, bytearray, str)):
        return ()
    ids: list[int] = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(ids)


def _string_tuple(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return (raw,) if raw else ()
    if not isinstance(raw, SequenceABC) or isinstance(raw, (bytes, bytearray, str)):
        return ()
    return tuple(str(item) for item in raw if str(item))


def _ids_text(values: Sequence[int]) -> str:
    return ", ".join(str(i) for i in values) if values else "None"


def _fingerprint(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReportRevisionSnapshot:
    project_id: int
    report_identifier: str
    revision_label: str
    report_path: str
    generated_at: str
    provenance_fingerprint: str
    validation_warnings: tuple[str, ...] = ()
    schema_history_selection_status: str = ""
    schema_history_available_ids: tuple[int, ...] = ()
    schema_history_selected_ids: tuple[int, ...] = ()
    schema_history_unknown_ids: tuple[int, ...] = ()
    schema_history_included_count: int = 0
    schema_history_diagnostic_row_count: int = 0
    operator_identifier: str = ""
    export_provenance: tuple[str, ...] = ()
    engineering_calculations_allowed: bool = False

    @classmethod
    def from_provenance(
        cls,
        provenance_summary,
        *,
        report_identifier: str = "combined_report",
        revision_label: str = "",
    ) -> "ReportRevisionSnapshot":
        payload = (
            provenance_summary.as_dict()
            if hasattr(provenance_summary, "as_dict")
            else dict(provenance_summary)
        )
        return cls(
            project_id=int(getattr(provenance_summary, "project_id", 0) or 0),
            report_identifier=report_identifier,
            revision_label=revision_label,
            report_path=str(getattr(provenance_summary, "report_path", "") or ""),
            generated_at=str(getattr(provenance_summary, "generated_at", "") or ""),
            provenance_fingerprint=_fingerprint(payload),
            validation_warnings=tuple(
                str(item)
                for item in (getattr(provenance_summary, "validation_warnings", ()) or ())
            ),
            schema_history_selection_status=str(
                getattr(provenance_summary, "schema_history_selection_status", "") or ""
            ),
            schema_history_available_ids=tuple(
                int(item)
                for item in (
                    getattr(provenance_summary, "schema_history_available_ids", ()) or ()
                )
            ),
            schema_history_selected_ids=tuple(
                int(item)
                for item in (
                    getattr(provenance_summary, "schema_history_selected_ids", ()) or ()
                )
            ),
            schema_history_unknown_ids=tuple(
                int(item)
                for item in (
                    getattr(provenance_summary, "schema_history_unknown_ids", ()) or ()
                )
            ),
            schema_history_included_count=int(
                getattr(provenance_summary, "schema_history_included_count", 0) or 0
            ),
            schema_history_diagnostic_row_count=int(
                getattr(provenance_summary, "schema_history_diagnostic_row_count", 0) or 0
            ),
            operator_identifier=str(
                getattr(provenance_summary, "operator_identifier", "") or ""
            ),
            export_provenance=tuple(
                str(item)
                for item in (getattr(provenance_summary, "export_provenance", ()) or ())
            ),
            engineering_calculations_allowed=bool(
                getattr(provenance_summary, "engineering_calculations_allowed", False)
            ),
        )

    @property
    def validation_warning_count(self) -> int:
        return len(self.validation_warnings)

    @property
    def fingerprint_short(self) -> str:
        return self.provenance_fingerprint[:12]

    @property
    def comparison_summary(self) -> tuple[str, ...]:
        return (
            f"Revision: {self.revision_label or 'Not assigned'}.",
            f"Report identifier: {self.report_identifier or 'Not recorded'}.",
            f"Provenance fingerprint: {self.fingerprint_short}.",
            f"Selection status: {self.schema_history_selection_status or 'Not recorded'}.",
            f"Selected schema history IDs: {_ids_text(self.schema_history_selected_ids)}.",
            f"Validation warnings: {self.validation_warning_count}.",
            "Comparison-ready snapshot only; full document diff is not implemented.",
            "Engineering calculations remain blocked.",
        )

    @property
    def operator_summary(self) -> tuple[str, ...]:
        warnings = self.validation_warnings or (
            "No validation warnings were captured for this revision.",
        )
        return (
            f"Report revision {self.revision_label or 'Not assigned'} generated {self.generated_at}.",
            f"Report path: {self.report_path or 'Not recorded'}.",
            f"Operator identifier: {self.operator_identifier or 'Not recorded'}.",
            f"Provenance fingerprint: {self.provenance_fingerprint}.",
            f"Schema-history selection status: {self.schema_history_selection_status or 'Not recorded'}.",
            f"Available history IDs: {_ids_text(self.schema_history_available_ids)}.",
            f"Selected history IDs: {_ids_text(self.schema_history_selected_ids)}.",
            f"Unknown requested history IDs: {_ids_text(self.schema_history_unknown_ids)}.",
            f"Included schema-history records: {self.schema_history_included_count}.",
            f"Propagated diagnostic rows: {self.schema_history_diagnostic_row_count}.",
            "Imported historical revision IDs are preserved exactly as recorded; no remapping is performed.",
            "Validation warning snapshot:",
            *warnings,
            "Comparison-ready summary:",
            *self.comparison_summary,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "report_identifier": self.report_identifier,
            "revision_label": self.revision_label,
            "report_path": self.report_path,
            "generated_at": self.generated_at,
            "provenance_fingerprint": self.provenance_fingerprint,
            "validation_warnings": list(self.validation_warnings),
            "schema_history_selection_status": self.schema_history_selection_status,
            "schema_history_available_ids": list(self.schema_history_available_ids),
            "schema_history_selected_ids": list(self.schema_history_selected_ids),
            "schema_history_unknown_ids": list(self.schema_history_unknown_ids),
            "schema_history_included_count": self.schema_history_included_count,
            "schema_history_diagnostic_row_count": self.schema_history_diagnostic_row_count,
            "operator_identifier": self.operator_identifier,
            "export_provenance": list(self.export_provenance),
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "comparison_summary": list(self.comparison_summary),
            "operator_summary": list(self.operator_summary),
        }


@dataclass(frozen=True, slots=True)
class ReportRevisionHistoryReview:
    project_id: int
    status: str
    engineering_calculations_allowed: bool
    items: tuple[ReportRevisionSnapshot, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == REPORT_REVISION_HISTORY_STATUS_AVAILABLE

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def latest_item(self) -> ReportRevisionSnapshot | None:
        return self.items[0] if self.items else None

    @property
    def operator_summary(self) -> tuple[str, ...]:
        if not self.items:
            return (
                "No report revision snapshots are available for this project.",
                "Engineering calculations remain blocked.",
            )
        latest = self.latest_item
        return (
            f"{self.item_count} report revision snapshot(s) available.",
            f"Latest revision: {latest.revision_label if latest else ''}.",
            "Revision review is read-only; full diff and destructive editing are not implemented.",
            "Engineering calculations remain blocked.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "ok": self.ok,
            "status": self.status,
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "item_count": self.item_count,
            "operator_summary": list(self.operator_summary),
            "items": [item.as_dict() for item in self.items],
        }


def build_report_revision_snapshot_item(row: Any) -> ReportRevisionSnapshot:
    summary = _payload(getattr(row, "summary_json", None))
    selection = _payload(getattr(row, "schema_history_selection_json", None))
    return ReportRevisionSnapshot(
        project_id=int(getattr(row, "project_id", 0) or summary.get("project_id") or 0),
        report_identifier=str(
            getattr(row, "report_identifier", "") or summary.get("report_identifier") or ""
        ),
        revision_label=str(
            getattr(row, "revision_label", "") or summary.get("revision_label") or ""
        ),
        report_path=str(getattr(row, "report_path", "") or summary.get("report_path") or ""),
        generated_at=_dt_text(getattr(row, "generated_at", "") or summary.get("generated_at")),
        provenance_fingerprint=str(
            getattr(row, "provenance_fingerprint", "")
            or summary.get("provenance_fingerprint")
            or ""
        ),
        validation_warnings=_string_tuple(
            getattr(row, "validation_warnings_json", None)
            or summary.get("validation_warnings")
        ),
        schema_history_selection_status=str(
            selection.get("status")
            or summary.get("schema_history_selection_status")
            or ""
        ),
        schema_history_available_ids=_ids_payload(
            selection.get("available_history_ids")
            or summary.get("schema_history_available_ids")
        ),
        schema_history_selected_ids=_ids_payload(
            selection.get("selected_history_ids")
            or summary.get("schema_history_selected_ids")
        ),
        schema_history_unknown_ids=_ids_payload(
            selection.get("unknown_history_ids")
            or summary.get("schema_history_unknown_ids")
        ),
        schema_history_included_count=int(
            selection.get("included_history_count")
            or summary.get("schema_history_included_count")
            or 0
        ),
        schema_history_diagnostic_row_count=int(
            selection.get("diagnostic_row_count")
            or summary.get("schema_history_diagnostic_row_count")
            or 0
        ),
        operator_identifier=str(summary.get("operator_identifier") or ""),
        export_provenance=_string_tuple(
            getattr(row, "export_provenance_json", None)
            or summary.get("export_provenance")
        ),
        engineering_calculations_allowed=bool(
            getattr(row, "engineering_calculations_allowed", False)
            or summary.get("engineering_calculations_allowed", False)
        ),
    )


def build_report_revision_history_review(
    project_id: int,
    rows: tuple[Any, ...] | list[Any],
) -> ReportRevisionHistoryReview:
    items = tuple(build_report_revision_snapshot_item(row) for row in rows)
    return ReportRevisionHistoryReview(
        project_id=project_id,
        status=(
            REPORT_REVISION_HISTORY_STATUS_AVAILABLE
            if items
            else REPORT_REVISION_HISTORY_STATUS_EMPTY
        ),
        engineering_calculations_allowed=False,
        items=items,
    )


def format_report_revision_snapshot_text(item: ReportRevisionSnapshot) -> str:
    return "\n".join(item.operator_summary)
