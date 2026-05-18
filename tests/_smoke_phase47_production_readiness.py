"""Phase-47 smoke - production/performance readiness diagnostics."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    PRODUCTION_READINESS_FORMAT,
    build_production_readiness_checklist,
)
from tests.pytest_smoke import PHASE_SMOKES


_tmp = Path(tempfile.mkdtemp(prefix="phase47_production_readiness_"))


def _write(path: Path, text: str = "phase47 fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _complete_repo_tree(root: Path) -> None:
    for path in (
        root / "run.py",
        root / "app" / "main.py",
        root / "app" / "config.py",
        root / "app" / "core" / "deployment.py",
        root / "app" / "core" / "benchmark_datasets.py",
        root / "app" / "core" / "production_readiness.py",
    ):
        _write(path)
    (root / "build").mkdir(parents=True, exist_ok=True)


def _runtime_paths(root: Path) -> dict[str, Path]:
    paths = {
        "reports": root / "reports",
        "exports": root / "exports",
        "logs": root / "logs",
        "diagnostics": root / "diagnostics",
        "temp": root / "tmp",
        "images": root / "images",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    print("=== 1) Complete production-readiness tree produces PASS diagnostics ===")
    complete_root = _tmp / "complete_repo"
    runtime_root = _tmp / "complete_runtime"
    _complete_repo_tree(complete_root)
    complete = build_production_readiness_checklist(
        repo_root=complete_root,
        user_data_dir=runtime_root,
        runtime_paths=_runtime_paths(runtime_root),
    )
    assert complete.status == DEPLOYMENT_CHECK_PASS
    assert complete.as_dict()["format"] == PRODUCTION_READINESS_FORMAT
    assert complete.local_only is True
    assert complete.read_only is True
    assert complete.telemetry_enabled is False
    assert complete.background_monitoring_enabled is False
    assert complete.cloud_upload_enabled is False
    assert complete.cleanup_performed is False
    assert complete.engineering_calculations_performed is False
    assert complete.performance_benchmarks_claimed is False
    print("  [PASS] local production-readiness artifacts are inventoried read-only")

    print("\n=== 2) Missing startup/diagnostic sources fail explicitly ===")
    incomplete_root = _tmp / "incomplete_repo"
    (incomplete_root / "app").mkdir(parents=True, exist_ok=True)
    incomplete = build_production_readiness_checklist(
        repo_root=incomplete_root,
        user_data_dir=_tmp / "incomplete_runtime",
        runtime_paths={},
    )
    assert incomplete.status == DEPLOYMENT_CHECK_FAIL
    assert any(item.key == "startup_diagnostic_sources" and item.failed
               for item in incomplete.checks)
    print("  [PASS] unavailable startup/diagnostic source files are blockers")

    print("\n=== 3) Current repository production-readiness payload is safe ===")
    repo_checklist = build_production_readiness_checklist(repo_root=_repo_root())
    assert repo_checklist.fail_count == 0
    assert "tests._smoke_phase47_production_readiness" in PHASE_SMOKES
    assert any(item.key == "large_local_artifacts" for item in repo_checklist.checks)
    assert any(item.key == "cache_inventory" for item in repo_checklist.checks)
    print("  [PASS] current repo diagnostics complete without blocking failures")

    print("\n=== 4) Payload remains local/offline and does not claim benchmarks ===")
    payload_text = _safe_text(repo_checklist.as_dict())
    assert "telemetry_enabled" in payload_text
    assert "background_monitoring_enabled" in payload_text
    assert "cloud_upload_enabled" in payload_text
    assert "cleanup_performed" in payload_text
    assert "performance_benchmarks_claimed" in payload_text
    assert "telemetry_enabled\": true" not in payload_text
    assert "background_monitoring_enabled\": true" not in payload_text
    assert "cloud_upload_enabled\": true" not in payload_text
    assert "cleanup_performed\": true" not in payload_text
    assert "engineering_calculations_performed\": true" not in payload_text
    assert "performance_benchmarks_claimed\": true" not in payload_text
    assert "fatigue_life" not in payload_text
    assert "rutting_life" not in payload_text
    assert "irc_compliance" not in payload_text
    print("  [PASS] payload does not enable telemetry, cleanup, cloud, calculations, or benchmark claims")

    print("\nPHASE 47 PRODUCTION READINESS SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
