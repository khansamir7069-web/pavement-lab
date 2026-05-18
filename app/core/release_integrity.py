"""Read-only release-integrity diagnostics for V1 hardening.

Phase 48 verifies that the local professionalization smoke chain, aggregate
smoke registration, and offline/read-only readiness markers remain coherent.
It does not run tests, change engineering logic, contact the network, or make
deployment/compliance claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.config import APP_DIR
from app.core.deployment import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    DEPLOYMENT_CHECK_WARN,
)


RELEASE_INTEGRITY_FORMAT = "sampave.release_integrity"
RELEASE_INTEGRITY_VERSION = "1.0"

REQUIRED_RELEASE_PHASE_SMOKES: tuple[str, ...] = (
    "tests._smoke_phase41_report_export_bundle",
    "tests._smoke_phase42_deployment_readiness",
    "tests._smoke_phase43_deployment_packaging_checklist",
    "tests._smoke_phase44_local_installer_preparation",
    "tests._smoke_phase45_deployment_regression_gate",
    "tests._smoke_phase46_benchmark_dataset_readiness",
    "tests._smoke_phase47_production_readiness",
    "tests._smoke_phase48_release_integrity",
    "tests._smoke_phase49_final_release",
)

_FORBIDDEN_ENABLED_MARKERS = (
    "telemetry_enabled\": true",
    "online_activation_enabled\": true",
    "cloud_deployment_enabled\": true",
    "cloud_upload_enabled\": true",
    "downloads_enabled\": true",
    "background_monitoring_enabled\": true",
    "cleanup_performed\": true",
    "engineering_calculations_performed\": true",
    "compliance_claims_generated\": true",
    "performance_benchmarks_claimed\": true",
)


def _timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True, slots=True)
class ReleaseIntegrityCheck:
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
class ReleaseIntegrityChecklist:
    generated_at: str
    repo_root: str
    checks: tuple[ReleaseIntegrityCheck, ...]
    local_only: bool = True
    read_only: bool = True
    tests_executed: bool = False
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
            f"Release integrity status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL check(s)."
            ),
            "Checklist is local-only, read-only, and registration-focused.",
            "No tests, telemetry, activation, cloud deployment, calculations, or compliance claims are performed.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": RELEASE_INTEGRITY_FORMAT,
            "format_version": RELEASE_INTEGRITY_VERSION,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "local_only": self.local_only,
            "read_only": self.read_only,
            "tests_executed": self.tests_executed,
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


def _module_to_path(repo_root: Path, module_name: str) -> Path:
    parts = module_name.split(".")
    return repo_root.joinpath(*parts).with_suffix(".py")


def _read_text(path: Path) -> tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8"), ""
    except Exception as exc:
        return "", str(exc)


def _phase_smoke_files_check(repo_root: Path) -> ReleaseIntegrityCheck:
    missing = [
        smoke for smoke in REQUIRED_RELEASE_PHASE_SMOKES
        if not _module_to_path(repo_root, smoke).is_file()
    ]
    status = DEPLOYMENT_CHECK_FAIL if missing else DEPLOYMENT_CHECK_PASS
    message = (
        f"Missing release-phase smoke module file(s): {', '.join(missing)}."
        if missing else
        "Phase 41-49 release/professionalization smoke module files are present."
    )
    return ReleaseIntegrityCheck(
        key="release_phase_smoke_files",
        label="Release phase smoke module files",
        status=status,
        message=message,
        path=str(repo_root / "tests"),
        details={
            "required_smokes": list(REQUIRED_RELEASE_PHASE_SMOKES),
            "missing_smokes": missing,
        },
    )


def _aggregate_registration_check(
    repo_root: Path,
    phase_smokes: Sequence[str],
) -> ReleaseIntegrityCheck:
    aggregate_path = repo_root / "tests" / "pytest_smoke.py"
    text, issue = _read_text(aggregate_path)
    if issue:
        return ReleaseIntegrityCheck(
            key="aggregate_smoke_registration",
            label="Aggregate smoke registration",
            status=DEPLOYMENT_CHECK_FAIL,
            message=f"Aggregate smoke module could not be read: {issue}",
            path=str(aggregate_path),
        )

    registered = tuple(phase_smokes)
    missing_from_tuple = [
        name for name in REQUIRED_RELEASE_PHASE_SMOKES
        if name not in registered
    ]
    missing_from_source = [
        name for name in REQUIRED_RELEASE_PHASE_SMOKES
        if name not in text
    ]
    duplicates = sorted({
        name for name in registered
        if registered.count(name) > 1
    })
    release_positions = [
        registered.index(name) for name in REQUIRED_RELEASE_PHASE_SMOKES
        if name in registered
    ]
    ordered = release_positions == sorted(release_positions)

    issues: list[str] = []
    issues.extend(f"not in PHASE_SMOKES tuple: {name}" for name in missing_from_tuple)
    issues.extend(f"not in pytest_smoke.py source: {name}" for name in missing_from_source)
    issues.extend(f"duplicate registration: {name}" for name in duplicates)
    if not ordered:
        issues.append("release phase smoke registrations are not in phase order")

    status = DEPLOYMENT_CHECK_FAIL if issues else DEPLOYMENT_CHECK_PASS
    message = (
        f"{len(issues)} aggregate smoke registration issue(s) found."
        if issues else
        "Phase 41-49 release/professionalization smokes are registered once and in order."
    )
    return ReleaseIntegrityCheck(
        key="aggregate_smoke_registration",
        label="Aggregate smoke registration",
        status=status,
        message=message,
        path=str(aggregate_path),
        details={
            "registered_count": len(registered),
            "required_release_smokes": list(REQUIRED_RELEASE_PHASE_SMOKES),
            "missing_from_tuple": missing_from_tuple,
            "missing_from_source": missing_from_source,
            "duplicates": duplicates,
            "phase_order_ok": ordered,
            "issues": issues,
        },
    )


def _regression_entrypoints_check(repo_root: Path) -> ReleaseIntegrityCheck:
    required = (
        repo_root / "tests" / "pytest_smoke.py",
        repo_root / "tests" / "test_excel_parity.py",
        repo_root / "tests" / "validation_harness.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    unreadable: list[str] = []
    for path in required:
        if not path.is_file():
            continue
        _text, issue = _read_text(path)
        if issue:
            unreadable.append(f"{path}: {issue}")
    status = DEPLOYMENT_CHECK_FAIL if missing or unreadable else DEPLOYMENT_CHECK_PASS
    message = (
        "One or more regression entrypoints are unavailable."
        if status == DEPLOYMENT_CHECK_FAIL else
        "Aggregate smoke, parity regression, and validation harness entrypoints are readable."
    )
    return ReleaseIntegrityCheck(
        key="regression_entrypoints",
        label="Regression entrypoint readiness",
        status=status,
        message=message,
        path=str(repo_root / "tests"),
        details={
            "checked_files": [str(path) for path in required],
            "missing_files": missing,
            "unreadable_files": unreadable,
            "tests_executed": False,
        },
    )


def _diagnostic_source_continuity_check(repo_root: Path) -> ReleaseIntegrityCheck:
    required = (
        repo_root / "app" / "core" / "deployment.py",
        repo_root / "app" / "core" / "benchmark_datasets.py",
        repo_root / "app" / "core" / "production_readiness.py",
        repo_root / "app" / "core" / "release_integrity.py",
        repo_root / "app" / "core" / "final_release.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    unreadable: list[str] = []
    for path in required:
        if not path.is_file():
            continue
        _text, issue = _read_text(path)
        if issue:
            unreadable.append(f"{path}: {issue}")
    status = DEPLOYMENT_CHECK_FAIL if missing or unreadable else DEPLOYMENT_CHECK_PASS
    message = (
        "One or more release-readiness diagnostic source files are unavailable."
        if status == DEPLOYMENT_CHECK_FAIL else
        "Deployment, dataset, production, release-integrity, and final-release diagnostics are readable."
    )
    return ReleaseIntegrityCheck(
        key="diagnostic_source_continuity",
        label="Release diagnostic source continuity",
        status=status,
        message=message,
        path=str(repo_root / "app" / "core"),
        details={
            "checked_files": [str(path) for path in required],
            "missing_files": missing,
            "unreadable_files": unreadable,
        },
    )


def _offline_integrity_marker_check(repo_root: Path) -> ReleaseIntegrityCheck:
    files = (
        repo_root / "app" / "core" / "deployment.py",
        repo_root / "app" / "core" / "benchmark_datasets.py",
        repo_root / "app" / "core" / "production_readiness.py",
        repo_root / "app" / "core" / "release_integrity.py",
        repo_root / "app" / "core" / "final_release.py",
        repo_root / "tests" / "_smoke_phase45_deployment_regression_gate.py",
        repo_root / "tests" / "_smoke_phase46_benchmark_dataset_readiness.py",
        repo_root / "tests" / "_smoke_phase47_production_readiness.py",
        repo_root / "tests" / "_smoke_phase48_release_integrity.py",
        repo_root / "tests" / "_smoke_phase49_final_release.py",
    )
    hits: list[str] = []
    unreadable: list[str] = []
    for path in files:
        if not path.is_file():
            unreadable.append(f"{path}: missing")
            continue
        text, issue = _read_text(path)
        if issue:
            unreadable.append(f"{path}: {issue}")
            continue
        lowered = text.lower()
        for marker in _FORBIDDEN_ENABLED_MARKERS:
            if marker in lowered:
                hits.append(f"{path}: {marker}")

    status = DEPLOYMENT_CHECK_FAIL if hits else (
        DEPLOYMENT_CHECK_WARN if unreadable else DEPLOYMENT_CHECK_PASS
    )
    if hits:
        message = f"{len(hits)} forbidden enabled marker(s) found."
    elif unreadable:
        message = "Some release-integrity source files could not be scanned."
    else:
        message = "Local/offline/read-only readiness markers remain disabled."
    return ReleaseIntegrityCheck(
        key="offline_integrity_markers",
        label="Local/offline release integrity markers",
        status=status,
        message=message,
        path=str(repo_root),
        details={
            "scanned_files": [str(path) for path in files],
            "forbidden_markers": list(_FORBIDDEN_ENABLED_MARKERS),
            "hits": hits,
            "unreadable_files": unreadable,
        },
    )


def build_release_integrity_checklist(
    *,
    repo_root: Path | str | None = None,
    phase_smokes: Sequence[str] = (),
) -> ReleaseIntegrityChecklist:
    """Build a read-only release-integrity checklist for V1 hardening."""
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    checks = (
        _phase_smoke_files_check(root),
        _aggregate_registration_check(root, tuple(phase_smokes)),
        _regression_entrypoints_check(root),
        _diagnostic_source_continuity_check(root),
        _offline_integrity_marker_check(root),
    )
    return ReleaseIntegrityChecklist(
        generated_at=_timestamp(),
        repo_root=str(root),
        checks=checks,
        local_only=True,
        read_only=True,
        tests_executed=False,
        telemetry_enabled=False,
        online_activation_enabled=False,
        cloud_deployment_enabled=False,
        internet_dependencies_enabled=False,
        engineering_calculations_performed=False,
        compliance_claims_generated=False,
    )
