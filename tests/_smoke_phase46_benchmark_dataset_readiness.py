"""Phase-46 smoke - benchmark/dataset readiness diagnostics."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    BENCHMARK_DATASET_READINESS_FORMAT,
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    build_benchmark_dataset_readiness_checklist,
)
from tests.pytest_smoke import PHASE_SMOKES


_tmp = Path(tempfile.mkdtemp(prefix="phase46_benchmark_dataset_readiness_"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _minimal_sample(name: str) -> dict:
    return {
        "name": name,
        "description": "Phase 46 fixture sample.",
        "engineering_intent": "Read-only dataset inventory smoke fixture.",
        "condition": {},
        "traffic": {},
        "structural": {},
        "expected": {},
    }


def _complete_repo_tree(root: Path) -> None:
    sample_name = "corpus_99_phase46_fixture"
    _write_json(
        root / "app" / "data" / "sample_projects" / f"{sample_name}.json",
        _minimal_sample(sample_name),
    )
    _write_json(
        root / "tests" / "golden" / "sample_projects" / f"{sample_name}.expected.json",
        {"name": sample_name, "condition": {"pci_band": "Fair"}},
    )
    _write_json(root / "tests" / "golden" / "shirdi_dbm.json", {"source": "phase46"})
    (root / "tests" / "validation_harness.py").parent.mkdir(parents=True, exist_ok=True)
    (root / "tests" / "validation_harness.py").write_text("# phase46 fixture\n", encoding="utf-8")
    (root / "tests" / "test_excel_parity.py").write_text("# phase46 fixture\n", encoding="utf-8")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "validation.md").write_text("# phase46 fixture\n", encoding="utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    print("=== 1) Complete benchmark/dataset tree produces PASS diagnostics ===")
    complete_root = _tmp / "complete_repo"
    _complete_repo_tree(complete_root)
    complete = build_benchmark_dataset_readiness_checklist(repo_root=complete_root)
    assert complete.status == DEPLOYMENT_CHECK_PASS
    assert complete.as_dict()["format"] == BENCHMARK_DATASET_READINESS_FORMAT
    assert complete.local_only is True
    assert complete.downloads_enabled is False
    assert complete.telemetry_enabled is False
    assert complete.engineering_calculations_performed is False
    assert complete.compliance_claims_generated is False
    print("  [PASS] approved local dataset artifacts are inventoried read-only")

    print("\n=== 2) Missing or unpaired benchmark artifacts fail explicitly ===")
    incomplete_root = _tmp / "incomplete_repo"
    sample_name = "corpus_98_missing_golden"
    _write_json(
        incomplete_root / "app" / "data" / "sample_projects" / f"{sample_name}.json",
        _minimal_sample(sample_name),
    )
    incomplete = build_benchmark_dataset_readiness_checklist(repo_root=incomplete_root)
    assert incomplete.status == DEPLOYMENT_CHECK_FAIL
    assert incomplete.fail_count >= 1
    assert any(item.key == "sample_project_golden_snapshots" and item.failed
               for item in incomplete.checks)
    print("  [PASS] missing golden snapshots are blockers, not silent fallbacks")

    print("\n=== 3) Current repository benchmark/dataset inventory is release-ready ===")
    repo_checklist = build_benchmark_dataset_readiness_checklist(repo_root=_repo_root())
    assert repo_checklist.status == DEPLOYMENT_CHECK_PASS
    sample_check = next(item for item in repo_checklist.checks
                        if item.key == "sample_project_payloads")
    golden_check = next(item for item in repo_checklist.checks
                        if item.key == "sample_project_golden_snapshots")
    assert sample_check.details["sample_count"] >= 5
    assert golden_check.details["golden_count"] == sample_check.details["sample_count"]
    assert "tests._smoke_phase46_benchmark_dataset_readiness" in PHASE_SMOKES
    print("  [PASS] canonical sample projects and golden snapshots are paired")

    print("\n=== 4) Benchmark readiness payload remains local/offline and audit-only ===")
    payload_text = _safe_text(repo_checklist.as_dict())
    assert "downloads_enabled" in payload_text
    assert "telemetry_enabled" in payload_text
    assert "engineering_calculations_performed" in payload_text
    assert "compliance_claims_generated" in payload_text
    assert "downloads_enabled\": true" not in payload_text
    assert "telemetry_enabled\": true" not in payload_text
    assert "engineering_calculations_performed\": true" not in payload_text
    assert "compliance_claims_generated\": true" not in payload_text
    assert "fatigue_life" not in payload_text
    assert "rutting_life" not in payload_text
    assert "irc_compliance" not in payload_text
    print("  [PASS] payload does not enable downloads, telemetry, calculations, or claims")

    print("\nPHASE 46 BENCHMARK DATASET READINESS SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
