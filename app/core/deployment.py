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
from app.core.iitpave.discovery import bundled_iitpave_exe_path, discover_iitpave_executable


DEPLOYMENT_MANIFEST_FORMAT = "sampave.deployment_manifest"
DEPLOYMENT_MANIFEST_VERSION = "1.0"
LOCAL_INSTALLER_PREPARATION_FORMAT = "sampave.local_installer_preparation"
LOCAL_INSTALLER_PREPARATION_VERSION = "1.0"

DEPLOYMENT_SEVERITY_INFO = "info"
DEPLOYMENT_SEVERITY_WARNING = "warning"
DEPLOYMENT_SEVERITY_ERROR = "error"

DEPLOYMENT_CHECK_PASS = "PASS"
DEPLOYMENT_CHECK_WARN = "WARN"
DEPLOYMENT_CHECK_FAIL = "FAIL"


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


@dataclass(frozen=True, slots=True)
class DeploymentChecklistItem:
    key: str
    label: str
    status: str
    message: str
    details: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_PASS

    @property
    def warning(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_WARN

    @property
    def failed(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_FAIL

    @property
    def operator_line(self) -> str:
        return f"{self.status} - {self.label}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class DeploymentPackagingChecklist:
    generated_at: str
    manifest: DeploymentManifest
    items: tuple[DeploymentChecklistItem, ...]

    @property
    def status(self) -> str:
        if any(item.failed for item in self.items):
            return DEPLOYMENT_CHECK_FAIL
        if any(item.warning for item in self.items):
            return DEPLOYMENT_CHECK_WARN
        return DEPLOYMENT_CHECK_PASS

    @property
    def ok(self) -> bool:
        return self.status != DEPLOYMENT_CHECK_FAIL

    @property
    def pass_count(self) -> int:
        return sum(1 for item in self.items if item.passed)

    @property
    def warn_count(self) -> int:
        return sum(1 for item in self.items if item.warning)

    @property
    def fail_count(self) -> int:
        return sum(1 for item in self.items if item.failed)

    @property
    def operator_summary(self) -> tuple[str, ...]:
        return (
            f"Deployment packaging checklist status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL item(s)."
            ),
            "Checklist is local-only, read-only, and diagnostics-only.",
            "No installer, activation, licensing, or cloud deployment is performed.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "manifest": self.manifest.as_dict(),
            "items": [item.as_dict() for item in self.items],
            "operator_summary": list(self.operator_summary),
        }


@dataclass(frozen=True, slots=True)
class LocalInstallerAssetCheck:
    key: str
    label: str
    path: str
    expected_type: str
    required: bool
    present: bool
    is_file: bool
    is_directory: bool
    readable: bool
    status: str
    message: str

    @property
    def passed(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_PASS

    @property
    def warning(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_WARN

    @property
    def failed(self) -> bool:
        return self.status == DEPLOYMENT_CHECK_FAIL

    @property
    def operator_line(self) -> str:
        return f"{self.status} - {self.label}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "path": self.path,
            "expected_type": self.expected_type,
            "required": self.required,
            "present": self.present,
            "is_file": self.is_file,
            "is_directory": self.is_directory,
            "readable": self.readable,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class LocalInstallerPreparationChecklist:
    generated_at: str
    repo_root: str
    assets: tuple[LocalInstallerAssetCheck, ...]
    build_executed: bool = False
    installer_created: bool = False
    cloud_deployment_enabled: bool = False
    online_activation_enabled: bool = False

    @property
    def status(self) -> str:
        if any(item.failed for item in self.assets):
            return DEPLOYMENT_CHECK_FAIL
        if any(item.warning for item in self.assets):
            return DEPLOYMENT_CHECK_WARN
        return DEPLOYMENT_CHECK_PASS

    @property
    def ok(self) -> bool:
        return self.status != DEPLOYMENT_CHECK_FAIL

    @property
    def pass_count(self) -> int:
        return sum(1 for item in self.assets if item.passed)

    @property
    def warn_count(self) -> int:
        return sum(1 for item in self.assets if item.warning)

    @property
    def fail_count(self) -> int:
        return sum(1 for item in self.assets if item.failed)

    @property
    def operator_summary(self) -> tuple[str, ...]:
        return (
            f"Local installer preparation status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL asset check(s)."
            ),
            "Checklist is read-only and source-tree based.",
            "No build, installer creation, activation, licensing, or cloud deployment is performed.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": LOCAL_INSTALLER_PREPARATION_FORMAT,
            "format_version": LOCAL_INSTALLER_PREPARATION_VERSION,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "build_executed": self.build_executed,
            "installer_created": self.installer_created,
            "cloud_deployment_enabled": self.cloud_deployment_enabled,
            "online_activation_enabled": self.online_activation_enabled,
            "assets": [item.as_dict() for item in self.assets],
            "operator_summary": list(self.operator_summary),
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


def _check_status(*, ok: bool, warn: bool = False) -> str:
    if not ok:
        return DEPLOYMENT_CHECK_FAIL
    if warn:
        return DEPLOYMENT_CHECK_WARN
    return DEPLOYMENT_CHECK_PASS


def _runtime_item(check: RuntimePathCheck) -> DeploymentChecklistItem:
    status = _check_status(ok=check.ok)
    message = "Directory exists and is writable." if check.ok else check.issue
    return DeploymentChecklistItem(
        key=f"runtime_path.{check.key}",
        label=f"{check.key.title()} runtime path",
        status=status,
        message=message or "Runtime path could not be validated.",
        details=check.as_dict(),
    )


def _metadata_item(manifest_payload: Mapping[str, Any]) -> DeploymentChecklistItem:
    app_meta = manifest_payload.get("application")
    if not isinstance(app_meta, Mapping):
        return DeploymentChecklistItem(
            key="application_metadata",
            label="Application version/build metadata",
            status=DEPLOYMENT_CHECK_WARN,
            message="Application metadata is incomplete; fallback manifest remains readable.",
            details={"available": False},
        )
    missing = [
        key for key in ("name", "product", "product_id", "version")
        if not str(app_meta.get(key) or "").strip()
    ]
    return DeploymentChecklistItem(
        key="application_metadata",
        label="Application version/build metadata",
        status=DEPLOYMENT_CHECK_WARN if missing else DEPLOYMENT_CHECK_PASS,
        message=(
            f"Missing metadata fields: {', '.join(missing)}."
            if missing
            else "Application version and product metadata are available."
        ),
        details={"application": dict(app_meta), "missing_fields": missing},
    )


def _runtime_metadata_item(manifest_payload: Mapping[str, Any]) -> DeploymentChecklistItem:
    runtime = manifest_payload.get("runtime")
    if not isinstance(runtime, Mapping):
        return DeploymentChecklistItem(
            key="runtime_metadata",
            label="Python/runtime metadata",
            status=DEPLOYMENT_CHECK_WARN,
            message="Runtime metadata is incomplete; checklist remains readable.",
            details={"available": False},
        )
    missing = [
        key for key in ("python", "platform", "frozen")
        if key not in runtime or runtime.get(key) in (None, "")
    ]
    return DeploymentChecklistItem(
        key="runtime_metadata",
        label="Python/runtime metadata",
        status=DEPLOYMENT_CHECK_WARN if missing else DEPLOYMENT_CHECK_PASS,
        message=(
            f"Missing runtime metadata fields: {', '.join(missing)}."
            if missing
            else "Python and platform metadata are available."
        ),
        details={"runtime": dict(runtime), "missing_fields": missing},
    )


def _default_repo_root(*, app_dir: Path | str | None = None) -> Path:
    root = Path(app_dir) if app_dir is not None else APP_DIR
    return root.parent if root.name == "app" else root


def _asset_readable(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.stat()
        if path.is_file():
            with path.open("rb") as fh:
                fh.read(1)
        elif path.is_dir():
            next(path.iterdir(), None)
        return True
    except StopIteration:
        return True
    except Exception:
        return False


def _installer_asset_specs() -> tuple[tuple[str, str, str, str, bool], ...]:
    return (
        ("entrypoint", "Application entry point", "run.py", "file", True),
        ("requirements", "Python dependency manifest", "requirements.txt", "file", True),
        ("launch_batch", "Local launch batch file", "Launch.bat", "file", True),
        ("setup_batch", "Local setup batch file", "Setup.bat", "file", True),
        ("build_batch", "Local build batch file", "Build.bat", "file", True),
        (
            "v1_pyinstaller_spec",
            "V1 PyInstaller spec",
            "build/installer/pyinstaller.spec",
            "file",
            True,
        ),
        (
            "iitpave_bundling_instruction",
            "IITPAVE bundling instruction",
            "build/installer/bundle_iitpave.md",
            "file",
            True,
        ),
        ("application_package", "Application package", "app", "directory", True),
        ("engineering_data", "Engineering data directory", "app/data", "directory", True),
        (
            "external_binary_dropin",
            "External binary drop-in directory",
            "app/external",
            "directory",
            True,
        ),
        (
            "report_template_dir",
            "Report template directory",
            "app/reports/templates",
            "directory",
            True,
        ),
        ("legacy_pyinstaller_spec", "Legacy PyInstaller spec", "build/pavement_lab.spec", "file", False),
        ("inno_setup_script", "Local installer script", "build/installer.iss", "file", False),
        ("build_powershell", "PowerShell build script", "build/build_exe.ps1", "file", False),
    )


def _check_local_installer_asset(
    *,
    repo_root: Path,
    key: str,
    label: str,
    relative_path: str,
    expected_type: str,
    required: bool,
) -> LocalInstallerAssetCheck:
    path = repo_root / relative_path
    present = path.exists()
    is_file = path.is_file() if present else False
    is_directory = path.is_dir() if present else False
    readable = _asset_readable(path)
    type_ok = (
        (expected_type == "file" and is_file)
        or (expected_type == "directory" and is_directory)
    )

    if not present:
        status = DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN
        message = "Required local packaging asset is missing." if required else (
            "Optional local packaging asset is missing."
        )
    elif not type_ok:
        status = DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN
        message = f"Asset exists but is not a {expected_type}."
    elif not readable:
        status = DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN
        message = "Asset exists but could not be read."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = f"{expected_type.title()} is present and readable."

    return LocalInstallerAssetCheck(
        key=key,
        label=label,
        path=str(path),
        expected_type=expected_type,
        required=required,
        present=present,
        is_file=is_file,
        is_directory=is_directory,
        readable=readable,
        status=status,
        message=message,
    )


def build_local_installer_preparation_checklist(
    *,
    repo_root: Path | str | None = None,
    app_dir: Path | str | None = None,
) -> LocalInstallerPreparationChecklist:
    """Inspect source-tree installer inputs without running a build."""
    root = Path(repo_root) if repo_root is not None else _default_repo_root(app_dir=app_dir)
    assets = tuple(
        _check_local_installer_asset(
            repo_root=root,
            key=key,
            label=label,
            relative_path=relative_path,
            expected_type=expected_type,
            required=required,
        )
        for key, label, relative_path, expected_type, required in _installer_asset_specs()
    )
    return LocalInstallerPreparationChecklist(
        generated_at=_timestamp(),
        repo_root=str(root),
        assets=assets,
        build_executed=False,
        installer_created=False,
        cloud_deployment_enabled=False,
        online_activation_enabled=False,
    )


def _installer_preparation_item(
    checklist: LocalInstallerPreparationChecklist,
) -> DeploymentChecklistItem:
    if checklist.fail_count:
        message = f"Local installer preparation has {checklist.fail_count} blocking asset issue(s)."
    elif checklist.warn_count:
        message = f"Local installer preparation has {checklist.warn_count} advisory asset warning(s)."
    else:
        message = "Local installer preparation assets are present and readable."
    return DeploymentChecklistItem(
        key="local_installer_preparation",
        label="Local installer preparation assets",
        status=checklist.status,
        message=message,
        details=checklist.as_dict(),
    )


def _report_export_readiness_item(
    diagnostics: DeploymentDiagnostics,
) -> DeploymentChecklistItem:
    checks = {
        check.key: check for check in diagnostics.runtime_paths
        if check.key in {"reports", "exports"}
    }
    missing = [key for key in ("reports", "exports") if key not in checks]
    failed = [check.key for check in checks.values() if not check.ok]
    status = (
        DEPLOYMENT_CHECK_FAIL if failed
        else DEPLOYMENT_CHECK_WARN if missing
        else DEPLOYMENT_CHECK_PASS
    )
    if failed:
        message = f"Report/export path checks failed: {', '.join(failed)}."
    elif missing:
        message = f"Report/export path checks missing: {', '.join(missing)}."
    else:
        message = "Report and export directories are ready for local deliverables."
    return DeploymentChecklistItem(
        key="report_export_readiness",
        label="Report/export directory readiness",
        status=status,
        message=message,
        details={
            "reports": checks.get("reports").as_dict() if "reports" in checks else None,
            "exports": checks.get("exports").as_dict() if "exports" in checks else None,
            "missing_checks": missing,
        },
    )


def _iitpave_discovery_item(
    *,
    app_dir: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> DeploymentChecklistItem:
    try:
        candidates = discover_iitpave_executable(
            env=env,
            include_path_search=False,
            app_dir=app_dir,
        )
    except Exception as exc:
        return DeploymentChecklistItem(
            key="iitpave_executable_discovery",
            label="Optional IITPAVE executable discovery",
            status=DEPLOYMENT_CHECK_WARN,
            message=f"IITPAVE discovery metadata is unavailable: {exc}",
            details={"available": False},
        )

    selected = next((candidate.path for candidate in candidates if candidate.is_file), None)
    status = DEPLOYMENT_CHECK_PASS if selected is not None else DEPLOYMENT_CHECK_WARN
    if selected is not None:
        message = f"IITPAVE executable candidate is available: {selected}"
    else:
        expected = bundled_iitpave_exe_path(app_dir=app_dir)
        message = (
            "No usable IITPAVE executable was found. This is optional at packaging "
            f"checklist time and execution remains blocked. Expected local bundle "
            f"location: {expected}"
        )
    return DeploymentChecklistItem(
        key="iitpave_executable_discovery",
        label="Optional IITPAVE executable discovery",
        status=status,
        message=message,
        details={
            "ok": selected is not None,
            "selected_path": str(selected) if selected else "",
            "candidates": [candidate.as_dict() for candidate in candidates],
            "execution_performed": False,
        },
    )


def build_deployment_packaging_checklist(
    *,
    diagnostics: DeploymentDiagnostics | None = None,
    manifest: DeploymentManifest | None = None,
    optional_metadata: Mapping[str, Any] | None = None,
    build_id: str | None = None,
    include_iitpave_discovery: bool = True,
    include_installer_preparation: bool = False,
    installer_repo_root: Path | str | None = None,
    iitpave_env: Mapping[str, str] | None = None,
    app_dir: Path | str | None = None,
) -> DeploymentPackagingChecklist:
    diag = diagnostics or validate_runtime_environment(create_missing=False)
    man = manifest or build_deployment_manifest(
        diagnostics=diag,
        optional_metadata=optional_metadata,
        build_id=build_id,
    )
    payload = man.as_dict()
    items: list[DeploymentChecklistItem] = [
        _runtime_item(check) for check in diag.runtime_paths
    ]
    items.extend([
        _report_export_readiness_item(diag),
        _metadata_item(payload),
        _runtime_metadata_item(payload),
    ])
    if include_iitpave_discovery:
        items.append(_iitpave_discovery_item(app_dir=app_dir or diag.app_dir, env=iitpave_env))
    if include_installer_preparation:
        installer_checklist = build_local_installer_preparation_checklist(
            repo_root=installer_repo_root,
            app_dir=app_dir or diag.app_dir,
        )
        items.append(_installer_preparation_item(installer_checklist))
    return DeploymentPackagingChecklist(
        generated_at=_timestamp(),
        manifest=man,
        items=tuple(items),
    )


def format_deployment_checklist_item_text(item: DeploymentChecklistItem) -> str:
    detail_text = json.dumps(item.details, indent=2, sort_keys=True, default=str)
    return "\n".join([
        f"Status: {item.status}",
        f"Check: {item.label}",
        f"Key: {item.key}",
        f"Message: {item.message}",
        "",
        "Details:",
        detail_text,
    ])


def format_deployment_packaging_checklist_text(
    checklist: DeploymentPackagingChecklist,
) -> str:
    lines = list(checklist.operator_summary)
    lines.append("")
    lines.extend(item.operator_line for item in checklist.items)
    return "\n".join(lines)


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
