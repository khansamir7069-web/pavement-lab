"""Phase-48 smoke - final release-integrity diagnostics."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    RELEASE_INTEGRITY_FORMAT,
    REQUIRED_RELEASE_PHASE_SMOKES,
    build_release_integrity_checklist,
)
from tests.pytest_smoke import PHASE_SMOKES


_tmp = Path(tempfile.mkdtemp(prefix="phase48_release_integrity_"))


def _write(path: Path, text: str = "phase48 fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _complete_repo_tree(root: Path) -> None:
    for module_name in REQUIRED_RELEASE_PHASE_SMOKES:
        _write(root.joinpath(*module_name.split(".")).with_suffix(".py"))
    for path in (
        root / "tests" / "pytest_smoke.py",
        root / "tests" / "test_excel_parity.py",
        root / "tests" / "validation_harness.py",
        root / "app" / "core" / "deployment.py",
        root / "app" / "core" / "benchmark_datasets.py",
        root / "app" / "core" / "production_readiness.py",
        root / "app" / "core" / "release_integrity.py",
        root / "app" / "core" / "final_release.py",
    ):
        _write(path)
    aggregate_source = "\n".join(REQUIRED_RELEASE_PHASE_SMOKES)
    _write(root / "tests" / "pytest_smoke.py", aggregate_source)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    print("=== 1) Complete release-integrity fixture tree produces PASS diagnostics ===")
    complete_root = _tmp / "complete_repo"
    _complete_repo_tree(complete_root)
    complete = build_release_integrity_checklist(
        repo_root=complete_root,
        phase_smokes=REQUIRED_RELEASE_PHASE_SMOKES,
    )
    assert complete.status == DEPLOYMENT_CHECK_PASS
    assert complete.as_dict()["format"] == RELEASE_INTEGRITY_FORMAT
    assert complete.local_only is True
    assert complete.read_only is True
    assert complete.tests_executed is False
    assert complete.telemetry_enabled is False
    assert complete.online_activation_enabled is False
    assert complete.cloud_deployment_enabled is False
    assert complete.internet_dependencies_enabled is False
    assert complete.engineering_calculations_performed is False
    assert complete.compliance_claims_generated is False
    print("  [PASS] release-integrity fixtures validate without running tests")

    print("\n=== 2) Missing aggregate registration fails explicitly ===")
    missing_registration = tuple(
        name for name in REQUIRED_RELEASE_PHASE_SMOKES
        if name != "tests._smoke_phase48_release_integrity"
    )
    incomplete = build_release_integrity_checklist(
        repo_root=complete_root,
        phase_smokes=missing_registration,
    )
    assert incomplete.status == DEPLOYMENT_CHECK_FAIL
    assert any(item.key == "aggregate_smoke_registration" and item.failed
               for item in incomplete.checks)
    print("  [PASS] omitted release smoke registration is a blocking issue")

    print("\n=== 3) Current repository release-integrity chain is complete ===")
    repo_checklist = build_release_integrity_checklist(
        repo_root=_repo_root(),
        phase_smokes=PHASE_SMOKES,
    )
    assert repo_checklist.status == DEPLOYMENT_CHECK_PASS
    assert tuple(REQUIRED_RELEASE_PHASE_SMOKES) == REQUIRED_RELEASE_PHASE_SMOKES
    for module_name in REQUIRED_RELEASE_PHASE_SMOKES:
        assert module_name in PHASE_SMOKES
    assert "tests._smoke_phase48_release_integrity" in PHASE_SMOKES
    assert "tests._smoke_phase49_final_release" in PHASE_SMOKES
    print("  [PASS] Phase 41-49 smoke modules are present and aggregated")

    print("\n=== 4) Release-integrity payload remains local/offline/read-only ===")
    payload_text = _safe_text(repo_checklist.as_dict())
    assert "tests_executed" in payload_text
    assert "telemetry_enabled" in payload_text
    assert "online_activation_enabled" in payload_text
    assert "cloud_deployment_enabled" in payload_text
    assert "internet_dependencies_enabled" in payload_text
    assert "engineering_calculations_performed" in payload_text
    assert "compliance_claims_generated" in payload_text
    assert "tests_executed\": true" not in payload_text
    assert "telemetry_enabled\": true" not in payload_text
    assert "online_activation_enabled\": true" not in payload_text
    assert "cloud_deployment_enabled\": true" not in payload_text
    assert "internet_dependencies_enabled\": true" not in payload_text
    assert "engineering_calculations_performed\": true" not in payload_text
    assert "compliance_claims_generated\": true" not in payload_text
    assert "fatigue_life" not in payload_text
    assert "rutting_life" not in payload_text
    assert "irc_compliance" not in payload_text
    print("  [PASS] payload does not enable tests, telemetry, cloud, calculations, or claims")

    print("\nPHASE 48 RELEASE INTEGRITY SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
