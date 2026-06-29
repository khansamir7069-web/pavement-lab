"""Phase-49 smoke - final V1 release packaging readiness."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.core import (
    DEPLOYMENT_CHECK_FAIL,
    FINAL_RELEASE_READINESS_FORMAT,
    REQUIRED_RELEASE_PHASE_SMOKES,
    build_final_release_readiness_checklist,
)
from tests.pytest_smoke import PHASE_SMOKES


_tmp = Path(tempfile.mkdtemp(prefix="phase49_final_release_"))


def _write(path: Path, text: str = "phase49 fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sample_payload(name: str) -> dict:
    return {
        "name": name,
        "description": "Phase 49 release fixture.",
        "engineering_intent": "Read-only final release packaging readiness fixture.",
        "condition": {},
        "traffic": {},
        "structural": {},
        "expected": {},
    }


def _aligned_installer_script() -> str:
    return """; Inno Setup script for RoadX Professional Suite.
#define MyAppName "RoadX Professional Suite"
#define MyAppVersion "2.2"
#define MyAppPublisher "SKM Technologies"
#define MyAppExeName "RoadX.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\\RoadX Professional Suite
DefaultGroupName=RoadX Professional Suite
OutputBaseFilename=RoadX_Professional_v2.2_Setup

[Files]
Source: "..\\dist\\RoadX\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
"""


def _complete_repo_tree(root: Path) -> None:
    for rel in (
        "run.py",
        "requirements.txt",
        "Launch.bat",
        "Setup.bat",
        "Build.bat",
        "README.md",
        "build/installer/pyinstaller.spec",
        "build/installer/bundle_iitpave.md",
        "build/installer.iss",
        "build/pavement_lab.spec",
        "build/build_exe.ps1",
        "app/__init__.py",
        "app/main.py",
        "app/config.py",
        "app/core/deployment.py",
        "app/core/benchmark_datasets.py",
        "app/core/production_readiness.py",
        "app/core/release_integrity.py",
        "app/core/final_release.py",
        "tests/pytest_smoke.py",
        "tests/test_excel_parity.py",
        "tests/validation_harness.py",
        "docs/validation.md",
    ):
        if rel == "build/installer.iss":
            _write(root / rel, _aligned_installer_script())
        else:
            _write(root / rel)
    for rel in (
        "app",
        "app/data",
        "app/external",
        "app/reports/templates",
        "build",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    sample_name = "corpus_99_phase49_fixture"
    _write_json(
        root / "app" / "data" / "sample_projects" / f"{sample_name}.json",
        _sample_payload(sample_name),
    )
    _write_json(
        root / "tests" / "golden" / "sample_projects" / f"{sample_name}.expected.json",
        {"name": sample_name, "condition": {"pci_band": "Fair"}},
    )
    _write_json(root / "tests" / "golden" / "shirdi_dbm.json", {"source": "phase49"})
    aggregate_source = "\n".join(REQUIRED_RELEASE_PHASE_SMOKES)
    _write(root / "tests" / "pytest_smoke.py", aggregate_source)
    for module_name in REQUIRED_RELEASE_PHASE_SMOKES:
        _write(root.joinpath(*module_name.split(".")).with_suffix(".py"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    print("=== 1) Complete final-release fixture tree has no blocking failures ===")
    complete_root = _tmp / "complete_repo"
    _complete_repo_tree(complete_root)
    complete = build_final_release_readiness_checklist(
        repo_root=complete_root,
        phase_smokes=REQUIRED_RELEASE_PHASE_SMOKES,
    )
    assert complete.status != DEPLOYMENT_CHECK_FAIL
    assert complete.fail_count == 0
    assert complete.as_dict()["format"] == FINAL_RELEASE_READINESS_FORMAT
    assert complete.local_only is True
    assert complete.read_only is True
    assert complete.build_executed is False
    assert complete.installer_created is False
    assert complete.manifest_written is False
    print("  [PASS] final release diagnostics compose without build or installer actions")

    print("\n=== 2) Missing release packaging asset fails explicitly ===")
    incomplete_root = _tmp / "incomplete_repo"
    _complete_repo_tree(incomplete_root)
    (incomplete_root / "build" / "installer" / "pyinstaller.spec").unlink()
    incomplete = build_final_release_readiness_checklist(
        repo_root=incomplete_root,
        phase_smokes=REQUIRED_RELEASE_PHASE_SMOKES,
    )
    assert incomplete.status == DEPLOYMENT_CHECK_FAIL
    assert any(item.key == "release_packaging_assets" and item.failed
               for item in incomplete.checks)
    print("  [PASS] missing required packaging files block final release readiness")

    print("\n=== 3) Installer script mismatch fails explicitly ===")
    mismatch_root = _tmp / "mismatch_repo"
    _complete_repo_tree(mismatch_root)
    _write(
        mismatch_root / "build" / "installer.iss",
        """#define MyAppName "Pavement Lab"
#define MyAppExeName "PavementLab.exe"
OutputBaseFilename=PavementLab-Setup
Source: "..\\dist\\PavementLab\\*"; DestDir: "{app}"
""",
    )
    mismatch = build_final_release_readiness_checklist(
        repo_root=mismatch_root,
        phase_smokes=REQUIRED_RELEASE_PHASE_SMOKES,
    )
    assert mismatch.status == DEPLOYMENT_CHECK_FAIL
    assert any(item.key == "release_packaging_assets" and item.failed
               for item in mismatch.checks)
    assert "pavementlab" in _safe_text(mismatch.as_dict())
    print("  [PASS] old PavementLab installer metadata blocks final release readiness")

    print("\n=== 4) Current repository final V1 readiness has no blocking failures ===")
    repo_checklist = build_final_release_readiness_checklist(
        repo_root=_repo_root(),
        phase_smokes=PHASE_SMOKES,
    )
    assert repo_checklist.fail_count == 0
    assert "tests._smoke_phase49_final_release" in PHASE_SMOKES
    assert tuple(REQUIRED_RELEASE_PHASE_SMOKES)[-1] == "tests._smoke_phase49_final_release"
    for key in (
        "release_packaging_assets",
        "release_manifest_continuity",
        "installer_preparation_rollup",
        "deployment_packaging_rollup",
        "benchmark_dataset_rollup",
        "production_readiness_rollup",
        "release_integrity_rollup",
    ):
        assert any(item.key == key for item in repo_checklist.checks)
    print("  [PASS] final release checklist covers packaging, manifests, and readiness rollups")

    print("\n=== 5) Final release payload remains local/offline/read-only ===")
    payload_text = _safe_text(repo_checklist.as_dict())
    for marker in (
        "build_executed",
        "installer_created",
        "manifest_written",
        "telemetry_enabled",
        "online_activation_enabled",
        "cloud_deployment_enabled",
        "internet_dependencies_enabled",
        "engineering_calculations_performed",
        "compliance_claims_generated",
    ):
        assert marker in payload_text
        assert f"{marker}\": true" not in payload_text
    assert "fatigue_life" not in payload_text
    assert "rutting_life" not in payload_text
    assert "irc_compliance" not in payload_text
    print("  [PASS] payload does not enable builds, activation, cloud, telemetry, calculations, or claims")

    print("\nPHASE 49 FINAL RELEASE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
