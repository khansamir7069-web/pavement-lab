"""Phase-45 smoke - deployment professionalization regression gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core import (
    DEPLOYMENT_CHECK_FAIL,
    build_local_installer_preparation_checklist,
)
from tests.pytest_smoke import PHASE_SMOKES


_REQUIRED_DEPLOYMENT_SMOKES = (
    "tests._smoke_phase41_report_export_bundle",
    "tests._smoke_phase42_deployment_readiness",
    "tests._smoke_phase43_deployment_packaging_checklist",
    "tests._smoke_phase44_local_installer_preparation",
    "tests._smoke_phase45_deployment_regression_gate",
)

_FORBIDDEN_DEPLOYMENT_MARKERS = (
    "cloud_deployment_enabled\": true",
    "online_activation_enabled\": true",
    "telemetry_enabled\": true",
    "internet_dependency_enabled\": true",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    print("=== 1) Deployment professionalization smokes are in the aggregate gate ===")
    missing = [name for name in _REQUIRED_DEPLOYMENT_SMOKES if name not in PHASE_SMOKES]
    assert not missing, f"Missing deployment smoke(s) from pytest aggregate: {missing}"
    print("  [PASS] Phase 41-45 deployment/professionalization smokes are aggregated")

    print("\n=== 2) Current source tree remains installer-preparation ready ===")
    checklist = build_local_installer_preparation_checklist(repo_root=_repo_root())
    assert checklist.status != DEPLOYMENT_CHECK_FAIL
    assert checklist.fail_count == 0
    assert any(item.key == "v1_pyinstaller_spec" and item.passed for item in checklist.assets)
    assert any(item.key == "iitpave_bundling_instruction" and item.passed for item in checklist.assets)
    print("  [PASS] required local installer-preparation assets are still readable")

    print("\n=== 3) Deployment readiness payload stays local/offline ===")
    payload_text = json.dumps(checklist.as_dict(), sort_keys=True, default=str).lower()
    assert checklist.build_executed is False
    assert checklist.installer_created is False
    assert checklist.cloud_deployment_enabled is False
    assert checklist.online_activation_enabled is False
    for marker in _FORBIDDEN_DEPLOYMENT_MARKERS:
        assert marker not in payload_text
    assert "fatigue_life" not in payload_text
    assert "rutting_life" not in payload_text
    assert "irc_compliance" not in payload_text
    print("  [PASS] payload does not enable cloud, activation, telemetry, or calculations")

    print("\nPHASE 45 DEPLOYMENT REGRESSION GATE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
