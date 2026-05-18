"""Local deployment/runtime readiness helpers.

Phase 42 prepares SamPave for local commercial deployment checks. The helpers
validate application/runtime directories and produce audit-friendly deployment
metadata. They do not implement cloud deployment, activation, licensing, or
installer orchestration.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app import __app_name__, __product_id__, __product_name__, __version__
from app.config import APP_DIR, REPORTS_DIR, USER_DATA_DIR


DEPLOYMENT_MANIFEST_FORMAT = "sampave.deployment_manifest"
DEPLOYMENT_MANIFEST_VERSION = "1.0"

DEPLOYMENT_SEVERITY_INFO = "info"
DEPLOYMENT_SEVERITY_WARNING = "warning"
DEPLOYMENT_SEVERITY_ERROR = "error"


def _timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True, slots=True)
class DeploymentIssue:
    severity: str
    field: str
    message: str

    @property
    def blocks_runtime(self) -> bool:
        return self.severity == DEPLOYMENT_SEVERITY_ERROR

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RuntimePathCheck:
    key: str
    path: str
    exists: bool
    is_directory: bool
    writable: bool
    created: bool = False
    required: bool = True
    issue: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and self.is_directory and self.writable

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "exists": self.exists,
            "is_directory": self.is_directory,
            "writable": self.writable,
            "created": self.created,
            "required": self.required,
            "ok": self.ok,
            "issue": self.issue,
        }


@dataclass(frozen=True, slots=True)
class DeploymentDiagnostics:
    checked_at: str
    app_dir: str
    user_data_dir: str
    runtime_paths: tuple[RuntimePathCheck, ...] = ()
    issues: tuple[DeploymentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.blocks_runtime for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == DEPLOYMENT_SEVERITY_WARNING for issue in self.issues)

    @property
    def operator_summary(self) -> tuple[str, ...]:
        if not self.issues:
            return (
                "Deployment runtime directories are present and writable.",
                "Deployment checks are local-only.",
            )
        return tuple(
            f"{issue.severity}: {issue.field}: {issue.message}"
            for issue in self.issues
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "ok": self.ok,
            "has_warnings": self.has_warnings,
            "app_dir": self.app_dir,
            "user_data_dir": self.user_data_dir,
            "runtime_paths": [item.as_dict() for item in self.runtime_paths],
            "issues": [issue.as_dict() for issue in self.issues],
            "operator_summary": list(self.operator_summary),
        }


@dataclass(frozen=True, slots=True)
class DeploymentManifest:
    generated_at: str
    build_id: str
    diagnostics: DeploymentDiagnostics
    optional_metadata: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return self.diagnostics.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": DEPLOYMENT_MANIFEST_FORMAT,
            "format_version": DEPLOYMENT_MANIFEST_VERSION,
            "generated_at": self.generated_at,
            "build_id": self.build_id,
            "application": {
                "name": __app_name__,
                "product": __product_name__,
                "product_id": __product_id__,
                "version": __version__,
            },
            "runtime": {
                "python": (
                    f"{sys.version_info.major}."
                    f"{sys.version_info.minor}."
                    f"{sys.version_info.micro}"
                ),
                "platform": platform.platform(),
                "frozen": bool(getattr(sys, "frozen", False)),
            },
            "optional_metadata": dict(self.optional_metadata),
            "diagnostics": self.diagnostics.as_dict(),
            "deployment_model": "local_only",
            "online_activation_enabled": False,
            "encrypted_licensing_enabled": False,
        }


def default_runtime_paths(
    *,
    user_data_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Path]:
    root = Path(user_data_dir) if user_data_dir is not None else USER_DATA_DIR
    return {
        "reports": Path(reports_dir) if reports_dir is not None else REPORTS_DIR,
        "exports": root / "exports",
        "logs": root / "logs",
        "diagnostics": root / "diagnostics",
        "temp": root / "tmp",
    }


def _check_writable(path: Path) -> tuple[bool, str]:
    probe = path / ".sampave_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, ""
    except Exception as exc:
        try:
            probe.unlink(missing_ok=True)
        except Exception:
            pass
        return False, str(exc)


def validate_runtime_path(
    key: str,
    path: Path,
    *,
    create_missing: bool = False,
    required: bool = True,
) -> RuntimePathCheck:
    path = Path(path)
    created = False
    issue = ""
    if not path.exists() and create_missing:
        try:
            path.mkdir(parents=True, exist_ok=True)
            created = True
        except Exception as exc:
            issue = f"Could not create runtime directory: {exc}"
    exists = path.exists()
    is_dir = path.is_dir() if exists else False
    writable = False
    if exists and is_dir:
        writable, write_issue = _check_writable(path)
        issue = issue or write_issue
    elif not issue:
        issue = "Runtime directory is missing." if not exists else "Path is not a directory."
    return RuntimePathCheck(
        key=key,
        path=str(path),
        exists=exists,
        is_directory=is_dir,
        writable=writable,
        created=created,
        required=required,
        issue=issue,
    )


def validate_runtime_environment(
    *,
    app_dir: Path | None = None,
    user_data_dir: Path | None = None,
    runtime_paths: Mapping[str, Path] | None = None,
    create_missing: bool = False,
) -> DeploymentDiagnostics:
    app_root = Path(app_dir) if app_dir is not None else APP_DIR
    user_root = Path(user_data_dir) if user_data_dir is not None else USER_DATA_DIR
    paths = dict(runtime_paths) if runtime_paths is not None else default_runtime_paths(
        user_data_dir=user_root,
    )
    issues: list[DeploymentIssue] = []

    if not app_root.exists():
        issues.append(DeploymentIssue(
            DEPLOYMENT_SEVERITY_ERROR,
            "app_dir",
            f"Application directory does not exist: {app_root}",
        ))
    elif not app_root.is_dir():
        issues.append(DeploymentIssue(
            DEPLOYMENT_SEVERITY_ERROR,
            "app_dir",
            f"Application path is not a directory: {app_root}",
        ))

    checks = tuple(
        validate_runtime_path(key, path, create_missing=create_missing)
        for key, path in paths.items()
    )
    for check in checks:
        if check.ok:
            continue
        severity = DEPLOYMENT_SEVERITY_ERROR if check.required else DEPLOYMENT_SEVERITY_WARNING
        issues.append(DeploymentIssue(severity, f"runtime_paths.{check.key}", check.issue))
    for check in checks:
        if check.created:
            issues.append(DeploymentIssue(
                DEPLOYMENT_SEVERITY_INFO,
                f"runtime_paths.{check.key}",
                f"Runtime directory created: {check.path}",
            ))

    return DeploymentDiagnostics(
        checked_at=_timestamp(),
        app_dir=str(app_root),
        user_data_dir=str(user_root),
        runtime_paths=checks,
        issues=tuple(issues),
    )


def build_deployment_manifest(
    *,
    diagnostics: DeploymentDiagnostics | None = None,
    optional_metadata: Mapping[str, Any] | None = None,
    build_id: str | None = None,
) -> DeploymentManifest:
    diag = diagnostics or validate_runtime_environment(create_missing=False)
    return DeploymentManifest(
        generated_at=_timestamp(),
        build_id=build_id or f"local-{__version__}",
        diagnostics=diag,
        optional_metadata=dict(optional_metadata or {}),
    )


def write_deployment_manifest(
    path: Path,
    manifest: DeploymentManifest,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return out


def startup_deployment_diagnostics() -> DeploymentDiagnostics:
    """Run non-fatal startup diagnostics and create missing runtime folders."""
    return validate_runtime_environment(create_missing=True)
