"""Final V1 release packaging readiness diagnostics.

Phase 49 composes the local/offline release-readiness checks built in Phases
42-48. It is intentionally read-only: no installer is created, no build is
run, no files are cleaned, no telemetry is emitted, and no engineering or
compliance verdicts are generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app import __version__
from app.config import APP_DIR
from app.core.benchmark_datasets import build_benchmark_dataset_readiness_checklist
from app.core.deployment import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    DEPLOYMENT_CHECK_WARN,
    DEPLOYMENT_MANIFEST_FORMAT,
    DEPLOYMENT_MANIFEST_VERSION,
    build_deployment_manifest,
    build_deployment_packaging_checklist,
    build_local_installer_preparation_checklist,
    validate_runtime_environment,
)
from app.core.production_readiness import build_production_readiness_checklist
from app.core.release_integrity import build_release_integrity_checklist


FINAL_RELEASE_READINESS_FORMAT = "roadx.final_release_readiness"
FINAL_RELEASE_READINESS_VERSION = "1.0"

_INNO_INSTALLER_REQUIRED_MARKERS = (
    '#define MyAppName "RoadX Professional Suite"',
    '#define MyAppPublisher "SKM Technologies"',
    '#define MyAppExeName "RoadX.exe"',
    "DefaultDirName={autopf}\\RoadX Professional Suite",
    "DefaultGroupName=RoadX Professional Suite",
    "OutputBaseFilename=RoadX_Professional_v2.2_Setup",
    'Source: "..\\dist\\RoadX\\*"',
)

_INNO_INSTALLER_FORBIDDEN_MARKERS = (
    "".join(["S", "A", "M", "P", "A", "V", "E"]),
    "".join(["S", "a", "m", "P", "a", "v", "e", ".", "e", "x", "e"]),
    "".join(["S", "A", "M", "P", "A", "V", "E", "-", "S", "e", "t", "u", "p"]),
    "".join(["d", "i", "s", "t", "\\", "S", "a", "m", "P", "a", "v", "e"]),
    "".join(["P", "a", "v", "e", "m", "e", "n", "t", " ", "L", "a", "b"]),
    "".join(["P", "a", "v", "e", "m", "e", "n", "t", "L", "a", "b", ".", "e", "x", "e"]),
    "".join(["P", "a", "v", "e", "m", "e", "n", "t", "L", "a", "b", "-", "S", "e", "t", "u", "p"]),
    "".join(["d", "i", "s", "t", "\\", "P", "a", "v", "e", "m", "e", "n", "t", "L", "a", "b"]),
)


def _timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True, slots=True)
class FinalReleaseCheck:
    key: str
    label: str
    status: str
    message: str
    path: str = ""
    details: Mapping[str, Any] | None = None

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
            "path": self.path,
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class FinalReleaseReadinessChecklist:
    generated_at: str
    repo_root: str
    checks: tuple[FinalReleaseCheck, ...]
    local_only: bool = True
    read_only: bool = True
    build_executed: bool = False
    installer_created: bool = False
    manifest_written: bool = False
    telemetry_enabled: bool = False
    online_activation_enabled: bool = False
    cloud_deployment_enabled: bool = False
    internet_dependencies_enabled: bool = False
    engineering_calculations_performed: bool = False
    compliance_claims_generated: bool = False

    @property
    def status(self) -> str:
        if any(item.failed for item in self.checks):
            return DEPLOYMENT_CHECK_FAIL
        if any(item.warning for item in self.checks):
            return DEPLOYMENT_CHECK_WARN
        return DEPLOYMENT_CHECK_PASS

    @property
    def ok(self) -> bool:
        return self.status != DEPLOYMENT_CHECK_FAIL

    @property
    def pass_count(self) -> int:
        return sum(1 for item in self.checks if item.passed)

    @property
    def warn_count(self) -> int:
        return sum(1 for item in self.checks if item.warning)

    @property
    def fail_count(self) -> int:
        return sum(1 for item in self.checks if item.failed)

    @property
    def operator_summary(self) -> tuple[str, ...]:
        return (
            f"Final V1 release readiness status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL check(s)."
            ),
            "Checklist is local-only, offline, and read-only.",
            "No build, installer creation, manifest write, telemetry, activation, cloud deployment, calculations, or compliance claims are performed.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": FINAL_RELEASE_READINESS_FORMAT,
            "format_version": FINAL_RELEASE_READINESS_VERSION,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "local_only": self.local_only,
            "read_only": self.read_only,
            "build_executed": self.build_executed,
            "installer_created": self.installer_created,
            "manifest_written": self.manifest_written,
            "telemetry_enabled": self.telemetry_enabled,
            "online_activation_enabled": self.online_activation_enabled,
            "cloud_deployment_enabled": self.cloud_deployment_enabled,
            "internet_dependencies_enabled": self.internet_dependencies_enabled,
            "engineering_calculations_performed": self.engineering_calculations_performed,
            "compliance_claims_generated": self.compliance_claims_generated,
            "operator_summary": list(self.operator_summary),
            "checks": [item.as_dict() for item in self.checks],
        }


def _default_repo_root() -> Path:
    return APP_DIR.parent if APP_DIR.name == "app" else APP_DIR


def _readable_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "File is missing."
    if not path.is_file():
        return False, "Path exists but is not a file."
    try:
        path.read_text(encoding="utf-8")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _release_packaging_assets_check(repo_root: Path) -> FinalReleaseCheck:
    required = (
        "run.py",
        "requirements.txt",
        "Launch.bat",
        "Setup.bat",
        "Build.bat",
        "README.md",
        "build/installer/pyinstaller.spec",
        "build/installer/bundle_iitpave.md",
        "build/installer.iss",
        "app/__init__.py",
    )
    issues: list[str] = []
    present: list[str] = []
    for rel in required:
        path = repo_root / rel
        ok, issue = _readable_file(path)
        if ok:
            present.append(rel)
        else:
            issues.append(f"{rel}: {issue}")
    installer_script = repo_root / "build" / "installer.iss"
    if installer_script.is_file():
        try:
            installer_text = installer_script.read_text(encoding="utf-8")
        except Exception as exc:
            issues.append(f"build/installer.iss: installer script could not be read: {exc}")
        else:
            missing_markers = [
                marker for marker in _INNO_INSTALLER_REQUIRED_MARKERS
                if marker not in installer_text
            ]
            forbidden_markers = [
                marker for marker in _INNO_INSTALLER_FORBIDDEN_MARKERS
                if marker in installer_text
            ]
            if missing_markers:
                issues.append(
                    "build/installer.iss: missing RoadX packaging marker(s): "
                    + ", ".join(missing_markers)
                )
            if forbidden_markers:
                issues.append(
                    "build/installer.iss: forbidden packaging marker(s) remain: "
                    + ", ".join(forbidden_markers)
                )
    status = DEPLOYMENT_CHECK_FAIL if issues else DEPLOYMENT_CHECK_PASS
    message = (
        f"{len(issues)} required local release packaging asset issue(s) found."
        if issues else
        "Required local release packaging assets are present and readable."
    )
    return FinalReleaseCheck(
        key="release_packaging_assets",
        label="Final V1 release packaging assets",
        status=status,
        message=message,
        path=str(repo_root),
        details={
            "required_assets": list(required),
            "present_assets": present,
            "installer_script_required_markers": list(_INNO_INSTALLER_REQUIRED_MARKERS),
            "installer_script_forbidden_markers": list(_INNO_INSTALLER_FORBIDDEN_MARKERS),
            "issues": issues,
            "build_executed": False,
            "installer_created": False,
        },
    )


def _release_manifest_continuity_check() -> FinalReleaseCheck:
    diagnostics = validate_runtime_environment(create_missing=False)
    manifest = build_deployment_manifest(diagnostics=diagnostics)
    payload = manifest.as_dict()
    issues: list[str] = []
    if payload.get("format") != DEPLOYMENT_MANIFEST_FORMAT:
        issues.append("deployment manifest format mismatch")
    if payload.get("format_version") != DEPLOYMENT_MANIFEST_VERSION:
        issues.append("deployment manifest format version mismatch")
    if not str(payload.get("build_id") or "").startswith(f"local-{__version__}"):
        issues.append("deployment manifest build_id does not match local version")
    if payload.get("deployment_model") != "local_only":
        issues.append("deployment manifest is not local_only")
    if payload.get("online_activation_enabled") is not False:
        issues.append("deployment manifest online activation flag is not false")
    if payload.get("encrypted_licensing_enabled") is not False:
        issues.append("deployment manifest licensing flag is not false")
    status = DEPLOYMENT_CHECK_FAIL if issues else DEPLOYMENT_CHECK_PASS
    message = (
        f"{len(issues)} deployment manifest continuity issue(s) found."
        if issues else
        "Deployment manifest metadata remains local-only and versioned."
    )
    return FinalReleaseCheck(
        key="release_manifest_continuity",
        label="Release manifest continuity",
        status=status,
        message=message,
        details={
            "manifest_format": payload.get("format"),
            "manifest_format_version": payload.get("format_version"),
            "build_id": payload.get("build_id"),
            "deployment_model": payload.get("deployment_model"),
            "online_activation_enabled": payload.get("online_activation_enabled"),
            "encrypted_licensing_enabled": payload.get("encrypted_licensing_enabled"),
            "manifest_written": False,
            "issues": issues,
        },
    )


def _status_rollup_check(key: str, label: str, source, *, allow_warn: bool = False) -> FinalReleaseCheck:
    status_value = getattr(source, "status", DEPLOYMENT_CHECK_FAIL)
    fail_count = int(getattr(source, "fail_count", 0) or 0)
    warn_count = int(getattr(source, "warn_count", 0) or 0)
    if fail_count:
        status = DEPLOYMENT_CHECK_FAIL
        message = f"{label} has {fail_count} blocking failure(s)."
    elif warn_count and not allow_warn:
        status = DEPLOYMENT_CHECK_WARN
        message = f"{label} has {warn_count} advisory warning(s)."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = f"{label} has no blocking failures."
    return FinalReleaseCheck(
        key=key,
        label=label,
        status=status,
        message=message,
        details={
            "source_status": status_value,
            "source_ok": bool(getattr(source, "ok", False)),
            "pass_count": int(getattr(source, "pass_count", 0) or 0),
            "warn_count": warn_count,
            "fail_count": fail_count,
            "allow_warn": allow_warn,
        },
    )


def build_final_release_readiness_checklist(
    *,
    repo_root: Path | str | None = None,
    phase_smokes: Sequence[str] = (),
) -> FinalReleaseReadinessChecklist:
    """Build the final local/offline V1 release-readiness checklist."""
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    installer = build_local_installer_preparation_checklist(repo_root=root)
    deployment = build_deployment_packaging_checklist(
        include_installer_preparation=True,
        installer_repo_root=root,
    )
    benchmark = build_benchmark_dataset_readiness_checklist(repo_root=root)
    production = build_production_readiness_checklist(repo_root=root)
    release_integrity = build_release_integrity_checklist(
        repo_root=root,
        phase_smokes=tuple(phase_smokes),
    )

    checks = (
        _release_packaging_assets_check(root),
        _release_manifest_continuity_check(),
        _status_rollup_check("installer_preparation_rollup", "Installer preparation diagnostics", installer),
        _status_rollup_check("deployment_packaging_rollup", "Deployment packaging diagnostics", deployment, allow_warn=True),
        _status_rollup_check("benchmark_dataset_rollup", "Benchmark/dataset diagnostics", benchmark),
        _status_rollup_check("production_readiness_rollup", "Production readiness diagnostics", production, allow_warn=True),
        _status_rollup_check("release_integrity_rollup", "Release integrity diagnostics", release_integrity),
    )
    return FinalReleaseReadinessChecklist(
        generated_at=_timestamp(),
        repo_root=str(root),
        checks=checks,
        local_only=True,
        read_only=True,
        build_executed=False,
        installer_created=False,
        manifest_written=False,
        telemetry_enabled=False,
        online_activation_enabled=False,
        cloud_deployment_enabled=False,
        internet_dependencies_enabled=False,
        engineering_calculations_performed=False,
        compliance_claims_generated=False,
    )
