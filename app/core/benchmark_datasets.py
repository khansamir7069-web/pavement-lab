"""Read-only benchmark/dataset readiness diagnostics.

Phase 46 inventories the local V1 benchmark and validation artifacts used for
release readiness. It does not download datasets, run engineering pipelines,
or certify IRC/MoRTH/IITPAVE compliance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app.config import APP_DIR
from app.core.deployment import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    DEPLOYMENT_CHECK_WARN,
)


BENCHMARK_DATASET_READINESS_FORMAT = "roadx.benchmark_dataset_readiness"
BENCHMARK_DATASET_READINESS_VERSION = "1.0"


def _timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass(frozen=True, slots=True)
class BenchmarkDatasetCheck:
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
class BenchmarkDatasetReadinessChecklist:
    generated_at: str
    repo_root: str
    checks: tuple[BenchmarkDatasetCheck, ...]
    local_only: bool = True
    downloads_enabled: bool = False
    telemetry_enabled: bool = False
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
            f"Benchmark/dataset readiness status: {self.status}.",
            (
                f"{self.pass_count} PASS, {self.warn_count} WARN, "
                f"{self.fail_count} FAIL check(s)."
            ),
            "Checklist is local-only and read-only.",
            "No benchmark values, compliance claims, downloads, telemetry, or calculations are generated.",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": BENCHMARK_DATASET_READINESS_FORMAT,
            "format_version": BENCHMARK_DATASET_READINESS_VERSION,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "status": self.status,
            "ok": self.ok,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "local_only": self.local_only,
            "downloads_enabled": self.downloads_enabled,
            "telemetry_enabled": self.telemetry_enabled,
            "engineering_calculations_performed": self.engineering_calculations_performed,
            "compliance_claims_generated": self.compliance_claims_generated,
            "operator_summary": list(self.operator_summary),
            "checks": [item.as_dict() for item in self.checks],
        }


def _default_repo_root() -> Path:
    return APP_DIR.parent if APP_DIR.name == "app" else APP_DIR


def _read_text(path: Path) -> tuple[bool, str]:
    try:
        path.read_text(encoding="utf-8")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _read_json(path: Path) -> tuple[Mapping[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, Mapping):
        return None, "JSON root is not an object."
    return payload, ""


def _file_check(key: str, label: str, path: Path, *, required: bool = True) -> BenchmarkDatasetCheck:
    if not path.exists():
        return BenchmarkDatasetCheck(
            key=key,
            label=label,
            status=DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN,
            message="Required file is missing." if required else "Optional file is missing.",
            path=str(path),
            details={"required": required, "present": False},
        )
    if not path.is_file():
        return BenchmarkDatasetCheck(
            key=key,
            label=label,
            status=DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN,
            message="Path exists but is not a file.",
            path=str(path),
            details={"required": required, "present": True, "is_file": False},
        )
    readable, issue = _read_text(path)
    return BenchmarkDatasetCheck(
        key=key,
        label=label,
        status=DEPLOYMENT_CHECK_PASS if readable else (
            DEPLOYMENT_CHECK_FAIL if required else DEPLOYMENT_CHECK_WARN
        ),
        message="File is present and readable." if readable else f"File is not readable: {issue}",
        path=str(path),
        details={
            "required": required,
            "present": True,
            "is_file": True,
            "readable": readable,
        },
    )


def _directory_check(key: str, label: str, path: Path) -> BenchmarkDatasetCheck:
    if not path.exists():
        return BenchmarkDatasetCheck(
            key=key,
            label=label,
            status=DEPLOYMENT_CHECK_FAIL,
            message="Required directory is missing.",
            path=str(path),
            details={"present": False},
        )
    if not path.is_dir():
        return BenchmarkDatasetCheck(
            key=key,
            label=label,
            status=DEPLOYMENT_CHECK_FAIL,
            message="Path exists but is not a directory.",
            path=str(path),
            details={"present": True, "is_directory": False},
        )
    try:
        entries = tuple(path.iterdir())
    except Exception as exc:
        return BenchmarkDatasetCheck(
            key=key,
            label=label,
            status=DEPLOYMENT_CHECK_FAIL,
            message=f"Directory is not readable: {exc}",
            path=str(path),
            details={"present": True, "is_directory": True, "readable": False},
        )
    return BenchmarkDatasetCheck(
        key=key,
        label=label,
        status=DEPLOYMENT_CHECK_PASS,
        message="Directory is present and readable.",
        path=str(path),
        details={"present": True, "is_directory": True, "entry_count": len(entries)},
    )


def _sample_payload_check(sample_dir: Path) -> tuple[BenchmarkDatasetCheck, tuple[str, ...]]:
    if not sample_dir.is_dir():
        return BenchmarkDatasetCheck(
            key="sample_project_payloads",
            label="Canonical sample project payloads",
            status=DEPLOYMENT_CHECK_FAIL,
            message="Sample project directory is unavailable.",
            path=str(sample_dir),
        ), ()

    sample_files = tuple(sorted(sample_dir.glob("corpus_*.json")))
    names: list[str] = []
    issues: list[str] = []
    required = {
        "name",
        "description",
        "engineering_intent",
        "condition",
        "traffic",
        "structural",
        "expected",
    }
    for path in sample_files:
        payload, issue = _read_json(path)
        if payload is None:
            issues.append(f"{path.name}: unreadable JSON ({issue})")
            continue
        names.append(path.stem)
        missing = sorted(required - set(payload))
        if missing:
            issues.append(f"{path.name}: missing required field(s): {', '.join(missing)}")
        if payload.get("name") != path.stem:
            issues.append(f"{path.name}: name field does not match filename stem")

    if not sample_files:
        status = DEPLOYMENT_CHECK_FAIL
        message = "No canonical sample project JSON files were found."
    elif issues:
        status = DEPLOYMENT_CHECK_FAIL
        message = f"{len(issues)} sample payload issue(s) found."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = f"{len(sample_files)} canonical sample project payload(s) are readable."
    return BenchmarkDatasetCheck(
        key="sample_project_payloads",
        label="Canonical sample project payloads",
        status=status,
        message=message,
        path=str(sample_dir),
        details={
            "sample_count": len(sample_files),
            "sample_names": names,
            "issues": issues,
            "engineering_values_computed": False,
        },
    ), tuple(names)


def _golden_payload_check(
    golden_dir: Path,
    sample_names: tuple[str, ...],
) -> tuple[BenchmarkDatasetCheck, tuple[str, ...]]:
    if not golden_dir.is_dir():
        return BenchmarkDatasetCheck(
            key="sample_project_golden_snapshots",
            label="Canonical sample golden snapshots",
            status=DEPLOYMENT_CHECK_FAIL,
            message="Golden snapshot directory is unavailable.",
            path=str(golden_dir),
        ), ()

    golden_files = tuple(sorted(golden_dir.glob("corpus_*.expected.json")))
    golden_names: list[str] = []
    issues: list[str] = []
    for path in golden_files:
        payload, issue = _read_json(path)
        if payload is None:
            issues.append(f"{path.name}: unreadable JSON ({issue})")
            continue
        stem = path.name.removesuffix(".expected.json")
        golden_names.append(stem)
        if payload.get("name") != stem:
            issues.append(f"{path.name}: name field does not match expected stem")

    missing_goldens = sorted(set(sample_names) - set(golden_names))
    orphan_goldens = sorted(set(golden_names) - set(sample_names))
    issues.extend(f"missing golden for sample: {name}" for name in missing_goldens)
    issues.extend(f"golden without sample payload: {name}" for name in orphan_goldens)

    if not golden_files:
        status = DEPLOYMENT_CHECK_FAIL
        message = "No canonical sample golden snapshots were found."
    elif issues:
        status = DEPLOYMENT_CHECK_FAIL
        message = f"{len(issues)} golden snapshot issue(s) found."
    else:
        status = DEPLOYMENT_CHECK_PASS
        message = f"{len(golden_files)} canonical golden snapshot(s) match sample payloads."
    return BenchmarkDatasetCheck(
        key="sample_project_golden_snapshots",
        label="Canonical sample golden snapshots",
        status=status,
        message=message,
        path=str(golden_dir),
        details={
            "golden_count": len(golden_files),
            "golden_names": golden_names,
            "missing_goldens": missing_goldens,
            "orphan_goldens": orphan_goldens,
            "issues": issues,
            "engineering_values_computed": False,
        },
    ), tuple(golden_names)


def _shirdi_golden_check(path: Path) -> BenchmarkDatasetCheck:
    payload, issue = _read_json(path)
    if payload is None:
        return BenchmarkDatasetCheck(
            key="excel_parity_golden_dataset",
            label="Excel parity golden dataset",
            status=DEPLOYMENT_CHECK_FAIL,
            message=f"Golden parity dataset is missing or unreadable: {issue}",
            path=str(path),
            details={"present": path.exists(), "engineering_values_computed": False},
        )
    return BenchmarkDatasetCheck(
        key="excel_parity_golden_dataset",
        label="Excel parity golden dataset",
        status=DEPLOYMENT_CHECK_PASS,
        message="Excel parity golden dataset is present and parseable.",
        path=str(path),
        details={
            "present": True,
            "top_level_keys": sorted(str(key) for key in payload.keys()),
            "engineering_values_computed": False,
        },
    )


def build_benchmark_dataset_readiness_checklist(
    *,
    repo_root: Path | str | None = None,
) -> BenchmarkDatasetReadinessChecklist:
    """Inventory local benchmark/dataset artifacts without running calculations."""
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    sample_projects_dir = root / "app" / "data" / "sample_projects"
    sample_goldens_dir = root / "tests" / "golden" / "sample_projects"
    shirdi_golden = root / "tests" / "golden" / "shirdi_dbm.json"

    checks: list[BenchmarkDatasetCheck] = [
        _directory_check(
            "sample_project_directory",
            "Canonical sample project directory",
            sample_projects_dir,
        ),
        _directory_check(
            "sample_golden_directory",
            "Canonical sample golden directory",
            sample_goldens_dir,
        ),
    ]
    sample_check, sample_names = _sample_payload_check(sample_projects_dir)
    golden_check, _golden_names = _golden_payload_check(sample_goldens_dir, sample_names)
    checks.extend([
        sample_check,
        golden_check,
        _shirdi_golden_check(shirdi_golden),
        _file_check(
            "validation_harness",
            "Validation harness",
            root / "tests" / "validation_harness.py",
        ),
        _file_check(
            "excel_parity_tests",
            "Excel parity regression tests",
            root / "tests" / "test_excel_parity.py",
        ),
        _file_check(
            "validation_documentation",
            "Validation framework documentation",
            root / "docs" / "validation.md",
        ),
    ])
    return BenchmarkDatasetReadinessChecklist(
        generated_at=_timestamp(),
        repo_root=str(root),
        checks=tuple(checks),
        local_only=True,
        downloads_enabled=False,
        telemetry_enabled=False,
        engineering_calculations_performed=False,
        compliance_claims_generated=False,
    )
