"""Consultancy report deliverable bundle packaging.

Phase 41 creates a local, read-only export bundle folder containing generated
report files and audit metadata manifests. It does not upload, encrypt,
license, or deploy anything.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app import __product_name__, __version__

from .iitpave_schema_history import (
    build_iitpave_schema_history_selection_audit_review,
)
from .report_revision import build_report_revision_history_review


REPORT_EXPORT_BUNDLE_FORMAT = "roadx.report_export_bundle"
REPORT_EXPORT_BUNDLE_VERSION = "1.0"


def _utcish_stamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _safe_name(value: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)
    return out.strip("._") or "artifact"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


@dataclass(frozen=True, slots=True)
class ReportBundleArtifact:
    kind: str
    bundle_path: str
    source_path: str = ""
    present: bool = True
    size_bytes: int = 0
    sha256: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "bundle_path": self.bundle_path,
            "source_path": self.source_path,
            "present": self.present,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ReportExportBundleManifest:
    bundle_id: str
    project_id: int
    created_at: str
    bundle_dir: str
    artifacts: tuple[ReportBundleArtifact, ...] = ()
    warnings: tuple[str, ...] = ()
    engineering_calculations_allowed: bool = False

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @property
    def present_artifact_count(self) -> int:
        return sum(1 for item in self.artifacts if item.present)

    @property
    def operator_summary(self) -> tuple[str, ...]:
        return (
            f"Bundle ID: {self.bundle_id}.",
            f"Project ID: {self.project_id}.",
            f"Created at: {self.created_at}.",
            f"Artifacts listed: {self.artifact_count}.",
            f"Artifacts present: {self.present_artifact_count}.",
            "Bundle is read-only deliverable packaging; no engineering calculations are enabled.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": REPORT_EXPORT_BUNDLE_FORMAT,
            "format_version": REPORT_EXPORT_BUNDLE_VERSION,
            "application": {
                "product": __product_name__,
                "version": __version__,
            },
            "bundle_id": self.bundle_id,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "bundle_dir": self.bundle_dir,
            "engineering_calculations_allowed": self.engineering_calculations_allowed,
            "operator_summary": list(self.operator_summary),
            "warnings": list(self.warnings),
            "artifacts": [item.as_dict() for item in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class ReportExportBundleResult:
    bundle_dir: Path
    manifest_path: Path
    manifest: ReportExportBundleManifest

    @property
    def ok(self) -> bool:
        return self.manifest.present_artifact_count > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bundle_dir": str(self.bundle_dir),
            "manifest_path": str(self.manifest_path),
            "manifest": self.manifest.as_dict(),
        }


def _copy_report_artifacts(
    *,
    bundle_dir: Path,
    report_paths: Sequence[Path],
) -> tuple[ReportBundleArtifact, ...]:
    reports_dir = bundle_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[ReportBundleArtifact] = []
    used_names: set[str] = set()
    for idx, raw_path in enumerate(report_paths, start=1):
        source = Path(raw_path)
        if not source.is_file():
            artifacts.append(ReportBundleArtifact(
                kind="generated_report",
                bundle_path="",
                source_path=str(source),
                present=False,
                note="Optional report artifact was not found and was not copied.",
            ))
            continue
        name = _safe_name(source.name)
        if name in used_names:
            name = f"{source.stem}_{idx}{source.suffix}"
        used_names.add(name)
        dest = reports_dir / name
        shutil.copy2(source, dest)
        artifacts.append(ReportBundleArtifact(
            kind="generated_report",
            bundle_path=_relative(dest, bundle_dir),
            source_path=str(source),
            present=True,
            size_bytes=dest.stat().st_size,
            sha256=_sha256(dest),
        ))
    return tuple(artifacts)


def build_report_export_bundle(
    bundle_dir: Path,
    db,
    project_id: int,
    *,
    report_paths: Sequence[Path | str] | None = None,
) -> ReportExportBundleResult:
    """Write a local deliverable bundle folder for one project.

    Missing reports or optional audit records are represented in the manifest
    and summary JSON files; they do not fail bundle generation.
    """
    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    created_at = _utcish_stamp()
    bundle_id = (
        f"ROADX-P{project_id}-"
        f"{created_at.replace('-', '').replace(':', '').replace(' ', 'T')}"
    )

    revision_rows = (
        db.list_report_revision_snapshots(project_id)
        if hasattr(db, "list_report_revision_snapshots")
        else []
    )
    revision_review = build_report_revision_history_review(project_id, revision_rows)
    audit_rows = (
        db.list_iitpave_schema_history_selection_audits(project_id)
        if hasattr(db, "list_iitpave_schema_history_selection_audits")
        else []
    )
    schema_audit_review = build_iitpave_schema_history_selection_audit_review(
        project_id,
        audit_rows,
    )

    report_candidates: list[Path] = []
    if report_paths is not None:
        report_candidates.extend(Path(path) for path in report_paths)
    for item in revision_review.items:
        if item.report_path:
            path = Path(item.report_path)
            if path not in report_candidates:
                report_candidates.append(path)

    artifacts = list(_copy_report_artifacts(
        bundle_dir=bundle_dir,
        report_paths=tuple(report_candidates),
    ))

    provenance_payload = {
        "bundle_id": bundle_id,
        "project_id": project_id,
        "created_at": created_at,
        "revision_provenance": [item.as_dict() for item in revision_review.items],
    }
    revision_payload = revision_review.as_dict()
    validation_payload = {
        "project_id": project_id,
        "warning_count": sum(item.validation_warning_count for item in revision_review.items),
        "warnings": [
            {
                "revision_label": item.revision_label,
                "warning": warning,
            }
            for item in revision_review.items
            for warning in item.validation_warnings
        ],
    }
    schema_audit_payload = schema_audit_review.as_dict()
    metadata_payload = {
        "format": REPORT_EXPORT_BUNDLE_FORMAT,
        "format_version": REPORT_EXPORT_BUNDLE_VERSION,
        "bundle_id": bundle_id,
        "project_id": project_id,
        "created_at": created_at,
        "optional_artifact_policy": (
            "Missing optional reports or audit records are listed without failing export."
        ),
        "engineering_calculations_allowed": False,
    }

    summary_specs: tuple[tuple[str, str, Mapping[str, Any]], ...] = (
        ("provenance_summaries", "provenance_summaries.json", provenance_payload),
        ("revision_snapshots", "revision_snapshots.json", revision_payload),
        ("validation_warnings", "validation_warnings.json", validation_payload),
        ("schema_history_audits", "schema_history_audits.json", schema_audit_payload),
        ("export_metadata", "export_metadata.json", metadata_payload),
    )
    for kind, filename, payload in summary_specs:
        path = _write_json(bundle_dir / filename, payload)
        artifacts.append(ReportBundleArtifact(
            kind=kind,
            bundle_path=_relative(path, bundle_dir),
            present=True,
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
        ))

    warnings: list[str] = []
    if not report_candidates:
        warnings.append("No generated report files were available for this bundle.")
    if not revision_review.items:
        warnings.append("No report revision snapshots were available for this project.")
    if not schema_audit_review.items:
        warnings.append("No schema-history selection audit records were available.")
    if any(not item.present for item in artifacts):
        warnings.append("One or more optional report artifacts were missing.")

    manifest = ReportExportBundleManifest(
        bundle_id=bundle_id,
        project_id=project_id,
        created_at=created_at,
        bundle_dir=str(bundle_dir),
        artifacts=tuple(artifacts),
        warnings=tuple(warnings),
        engineering_calculations_allowed=False,
    )
    manifest_path = _write_json(bundle_dir / "manifest.json", manifest.as_dict())
    return ReportExportBundleResult(
        bundle_dir=bundle_dir,
        manifest_path=manifest_path,
        manifest=manifest,
    )
