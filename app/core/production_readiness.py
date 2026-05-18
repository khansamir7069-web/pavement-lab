"""Read-only production/performance readiness diagnostics.

Phase 47 inspects local runtime and repository artifact growth for V1 release
readiness. It does not benchmark calculations, delete files, run background
monitors, upload telemetry, or contact any network service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app.config import APP_DIR, IMAGES_DIR, REPORTS_DIR, USER_DATA_DIR
from app.core.deployment import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    DEPLOYMENT_CHECK_WARN,
)


PRODUCTION_READINESS_FORMAT = "sampave.production_readiness"
PRODUCTION_READINESS_VERSION = "1.0"

SCAN_FILE_LIMIT = 10000
DIR_WARN_SIZE_BYTES = 250 * 1024 * 1024
DIR_FAIL_SIZE_BYTES = 2 * 1024 * 1024 * 1024
DIR_WARN_FILE_COUNT = 5000
DIR_FAIL_FILE_COUNT = 50000
FILE_WARN_SIZE_BYTES = 100 * 1024 * 1024
FILE_FAIL_SIZE_BYTES = 1024 * 1024 * 1024


def _timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True, slots=True)
class ProductionReadinessCheck:
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
class ProductionReadinessChecklist:
    generated_at: str
    repo_root: str
    user_data_dir: str
    checks: tuple[ProductionReadinessCheck, ...]
    local_only: bool = True
    read_only: bool = True
    telemetry_enabled: bool = False
    background_monitoring_enabled: bool = False
    cloud_upload_enabled: bool = False
    cleanup_performed: bool = False
    engineering_calculations_performed: bool = False
    performance_benchmarks_claimed: bool = False

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
            f"Production readiness status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL check(s)."
            ),
            "Checklist is local-only, read-only, and advisory.",
            "No telemetry, background monitoring, cleanup, cloud upload, calculations, or benchmark claims are performed.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": PRODUCTION_READINESS_FORMAT,
            "format_version": PRODUCTION_READINESS_VERSION,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "user_data_dir": self.user_data_dir,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "local_only": self.local_only,
            "read_only": self.read_only,
            "telemetry_enabled": self.telemetry_enabled,
            "background_monitoring_enabled": self.background_monitoring_enabled,
            "cloud_upload_enabled": self.cloud_upload_enabled,
            "cleanup_performed": self.cleanup_performed,
            "engineering_calculations_performed": self.engineering_calculations_performed,
            "performance_benchmarks_claimed": self.performance_benchmarks_claimed,
            "operator_summary": list(self.operator_summary),
            "checks": [item.as_dict() for item in self.checks],
        }


def _default_repo_root() -> Path:
    return APP_DIR.parent if APP_DIR.name == "app" else APP_DIR


def _directory_stats(path: Path, *, file_limit: int = SCAN_FILE_LIMIT) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "present": path.exists(),
        "is_directory": path.is_dir() if path.exists() else False,
        "readable": False,
        "file_count": 0,
        "directory_count": 0,
        "total_size_bytes": 0,
        "largest_files": [],
        "scan_truncated": False,
        "issue": "",
    }
    if not stats["present"] or not stats["is_directory"]:
        return stats
    largest: list[tuple[int, str]] = []
    try:
        for item in path.rglob("*"):
            if item.is_dir():
                stats["directory_count"] += 1
                continue
            if not item.is_file():
                continue
            stats["file_count"] += 1
            try:
                size = item.stat().st_size
            except Exception:
                continue
            stats["total_size_bytes"] += size
            largest.append((size, str(item)))
            largest.sort(reverse=True)
            del largest[5:]
            if stats["file_count"] >= file_limit:
                stats["scan_truncated"] = True
                break
        stats["readable"] = True
    except Exception as exc:
        stats["issue"] = str(exc)
    stats["largest_files"] = [
        {"path": file_path, "size_bytes": size}
        for size, file_path in largest
    ]
    return stats


def _status_for_directory_stats(stats: Mapping[str, Any], *, required: bool) -> tuple[str, str]:
    if not stats.get("present"):
        return (
            DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN,
            "Directory is missing." if required else "Optional directory is missing.",
        )
    if not stats.get("is_directory"):
        return (
            DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN,
            "Path exists but is not a directory.",
        )
    if not stats.get("readable"):
        return (
            DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN,
            f"Directory could not be read: {stats.get('issue') or 'unknown error'}",
        )
    total_size = int(stats.get("total_size_bytes") or 0)
    file_count = int(stats.get("file_count") or 0)
    if total_size >= DIR_FAIL_SIZE_BYTES or file_count >= DIR_FAIL_FILE_COUNT:
        return DEPLOYMENT_CHECK_FAIL, "Directory growth exceeds blocking readiness threshold."
    if (
        total_size >= DIR_WARN_SIZE_BYTES
        or file_count >= DIR_WARN_FILE_COUNT
        or stats.get("scan_truncated")
    ):
        return DEPLOYMENT_CHECK_WARN, "Directory growth should be reviewed before release."
    return DEPLOYMENT_CHECK_PASS, "Directory size and file count are within advisory readiness thresholds."


def _directory_growth_check(
    key: str,
    label: str,
    path: Path,
    *,
    required: bool = False,
) -> ProductionReadinessCheck:
    stats = _directory_stats(path)
    status, message = _status_for_directory_stats(stats, required=required)
    details = dict(stats)
    details.update({
        "required": required,
        "warn_size_bytes": DIR_WARN_SIZE_BYTES,
        "fail_size_bytes": DIR_FAIL_SIZE_BYTES,
        "warn_file_count": DIR_WARN_FILE_COUNT,
        "fail_file_count": DIR_FAIL_FILE_COUNT,
        "cleanup_performed": False,
    })
    return ProductionReadinessCheck(
        key=key,
        label=label,
        status=status,
        message=message,
        path=str(path),
        details=details,
    )


def _cache_inventory_check(repo_root: Path) -> ProductionReadinessCheck:
    cache_dirs: list[Path] = []
    try:
        for item in repo_root.rglob("*"):
            if item.is_dir() and item.name in {"__pycache__", ".pytest_cache"}:
                cache_dirs.append(item)
    except Exception as exc:
        return ProductionReadinessCheck(
            key="cache_inventory",
            label="Local cache directory inventory",
            status=DEPLOYMENT_CHECK_WARN,
            message=f"Cache directory inventory could not be completed: {exc}",
            path=str(repo_root),
            details={"cleanup_performed": False},
        )

    total_size = 0
    total_files = 0
    for cache_dir in cache_dirs:
        stats = _directory_stats(cache_dir)
        total_size += int(stats.get("total_size_bytes") or 0)
        total_files += int(stats.get("file_count") or 0)

    if total_size >= DIR_FAIL_SIZE_BYTES or total_files >= DIR_FAIL_FILE_COUNT:
        status = DEPLOYMENT_CHECK_FAIL
        message = "Local cache growth exceeds blocking readiness threshold."
    elif total_size >= DIR_WARN_SIZE_BYTES or total_files >= DIR_WARN_FILE_COUNT:
        status = DEPLOYMENT_CHECK_WARN
        message = "Local cache growth should be reviewed before release."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = "Local cache footprint is within advisory readiness thresholds."
    return ProductionReadinessCheck(
        key="cache_inventory",
        label="Local cache directory inventory",
        status=status,
        message=message,
        path=str(repo_root),
        details={
            "cache_directory_count": len(cache_dirs),
            "total_size_bytes": total_size,
            "file_count": total_files,
            "warn_size_bytes": DIR_WARN_SIZE_BYTES,
            "fail_size_bytes": DIR_FAIL_SIZE_BYTES,
            "warn_file_count": DIR_WARN_FILE_COUNT,
            "fail_file_count": DIR_FAIL_FILE_COUNT,
            "cleanup_performed": False,
        },
    )


def _large_file_inventory_check(repo_root: Path) -> ProductionReadinessCheck:
    large: list[dict[str, Any]] = []
    unreadable: list[str] = []
    try:
        for item in repo_root.rglob("*"):
            if not item.is_file():
                continue
            try:
                size = item.stat().st_size
            except Exception as exc:
                unreadable.append(f"{item}: {exc}")
                continue
            if size >= FILE_WARN_SIZE_BYTES:
                large.append({"path": str(item), "size_bytes": size})
    except Exception as exc:
        return ProductionReadinessCheck(
            key="large_local_artifacts",
            label="Large local artifact inventory",
            status=DEPLOYMENT_CHECK_WARN,
            message=f"Large-file inventory could not be completed: {exc}",
            path=str(repo_root),
            details={"cleanup_performed": False},
        )

    fail_count = sum(1 for item in large if int(item["size_bytes"]) >= FILE_FAIL_SIZE_BYTES)
    if fail_count:
        status = DEPLOYMENT_CHECK_FAIL
        message = f"{fail_count} local artifact(s) exceed blocking readiness threshold."
    elif large or unreadable:
        status = DEPLOYMENT_CHECK_WARN
        message = f"{len(large)} large artifact(s) should be reviewed before release."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = "No large local artifacts exceed advisory threshold."
    return ProductionReadinessCheck(
        key="large_local_artifacts",
        label="Large local artifact inventory",
        status=status,
        message=message,
        path=str(repo_root),
        details={
            "large_file_count": len(large),
            "large_files": large[:25],
            "unreadable_files": unreadable[:25],
            "warn_file_size_bytes": FILE_WARN_SIZE_BYTES,
            "fail_file_size_bytes": FILE_FAIL_SIZE_BYTES,
            "cleanup_performed": False,
        },
    )


def _startup_source_check(repo_root: Path) -> ProductionReadinessCheck:
    required = (
        repo_root / "run.py",
        repo_root / "app" / "main.py",
        repo_root / "app" / "config.py",
        repo_root / "app" / "core" / "deployment.py",
        repo_root / "app" / "core" / "benchmark_datasets.py",
        repo_root / "app" / "core" / "production_readiness.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    unreadable: list[str] = []
    for path in required:
        if not path.is_file():
            continue
        try:
            path.read_text(encoding="utf-8")
        except Exception as exc:
            unreadable.append(f"{path}: {exc}")
    if missing or unreadable:
        status = DEPLOYMENT_CHECK_FAIL
        message = "One or more startup/diagnostic source files are unavailable."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = "Startup and diagnostic source files are present and readable."
    return ProductionReadinessCheck(
        key="startup_diagnostic_sources",
        label="Startup/diagnostic source readiness",
        status=status,
        message=message,
        path=str(repo_root),
        details={
            "checked_files": [str(path) for path in required],
            "missing_files": missing,
            "unreadable_files": unreadable,
            "imports_executed": False,
        },
    )


def _runtime_directory_specs(user_data_dir: Path) -> tuple[tuple[str, str, Path, bool], ...]:
    return (
        ("runtime_reports_growth", "Reports directory growth", REPORTS_DIR, False),
        ("runtime_exports_growth", "Exports directory growth", user_data_dir / "exports", False),
        ("runtime_logs_growth", "Logs directory growth", user_data_dir / "logs", False),
        ("runtime_diagnostics_growth", "Diagnostics directory growth", user_data_dir / "diagnostics", False),
        ("runtime_temp_growth", "Temporary directory growth", user_data_dir / "tmp", False),
        ("runtime_images_growth", "Image evidence directory growth", IMAGES_DIR, False),
    )


def build_production_readiness_checklist(
    *,
    repo_root: Path | str | None = None,
    user_data_dir: Path | str | None = None,
    runtime_paths: Mapping[str, Path | str] | None = None,
) -> ProductionReadinessChecklist:
    """Inspect local production-readiness signals without changing files."""
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    user_root = Path(user_data_dir) if user_data_dir is not None else USER_DATA_DIR
    runtime_specs = (
        tuple(
            (f"runtime_{key}_growth", f"{key.title()} runtime directory growth", Path(path), False)
            for key, path in runtime_paths.items()
        )
        if runtime_paths is not None
        else _runtime_directory_specs(user_root)
    )

    checks: list[ProductionReadinessCheck] = [
        _startup_source_check(root),
        _directory_growth_check("repository_build_artifacts", "Build artifact directory growth", root / "build"),
        _directory_growth_check("repository_source_tree", "Application source tree growth", root / "app", required=True),
    ]
    checks.extend(
        _directory_growth_check(key, label, path, required=required)
        for key, label, path, required in runtime_specs
    )
    checks.extend([
        _cache_inventory_check(root),
        _large_file_inventory_check(root),
    ])

    return ProductionReadinessChecklist(
        generated_at=_timestamp(),
        repo_root=str(root),
        user_data_dir=str(user_root),
        checks=tuple(checks),
        local_only=True,
        read_only=True,
        telemetry_enabled=False,
        background_monitoring_enabled=False,
        cloud_upload_enabled=False,
        cleanup_performed=False,
        engineering_calculations_performed=False,
        performance_benchmarks_claimed=False,
    )
