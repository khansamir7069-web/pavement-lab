"""Phase-24 smoke - IITPAVE dry-run execution readiness checks.

Uses temporary non-engineering scripts/files only to exercise launch-safety
behavior. No IITPAVE engineering input is generated and no output is parsed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from app.core import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPaveDryRunConfig,
    IITPaveRunnerConfig,
    check_iitpave_dry_run_readiness,
    select_iitpave_runner,
)


def _fake_app_dir() -> Path:
    root = Path(tempfile.mkdtemp(prefix="phase24_iitpave_"))
    (root / "external" / "iitpave").mkdir(parents=True)
    return root


def _write_probe_script(path: Path, *, exit_code: int = 0, sleep: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".cmd")
        if sleep:
            body = "@echo off\r\nping 127.0.0.1 -n 6 >nul\r\nexit /b 0\r\n"
        else:
            body = (
                "@echo off\r\n"
                "echo NON_ENGINEERING_DRY_RUN_PROBE\r\n"
                f"exit /b {exit_code}\r\n"
            )
    else:
        path = path.with_suffix("")
        if sleep:
            body = "#!/bin/sh\nsleep 5\nexit 0\n"
        else:
            body = (
                "#!/bin/sh\n"
                "echo NON_ENGINEERING_DRY_RUN_PROBE\n"
                f"exit {exit_code}\n"
            )
    path.write_text(body, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    return path


def _write_bad_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a valid executable image", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    return path


def _selection(path: Path, app_dir: Path, *, working_dir: Path | None = None):
    return select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(path),
            timeout_sec=10.0,
            working_dir=str(working_dir) if working_dir else "",
        ),
        app_dir=app_dir,
        env={},
    )


def main() -> int:
    print("=== 1) Blocked runner selection refuses dry-run ===")
    app_dir = _fake_app_dir()
    blocked_selection = select_iitpave_runner(
        IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL),
        app_dir=app_dir,
        env={},
    )
    blocked = check_iitpave_dry_run_readiness(blocked_selection)
    assert blocked.blocked is True
    assert blocked.launch_attempted is False
    assert "No IITPAVE executable" in blocked.blocked_reason
    print("  [PASS] invalid runner selection blocks dry-run before launch")

    print("\n=== 2) Stub runner selection refuses dry-run ===")
    stub_selection = select_iitpave_runner(app_dir=app_dir, env={})
    stub = check_iitpave_dry_run_readiness(stub_selection)
    assert stub.blocked is True
    assert "external_exe" in stub.blocked_reason
    assert stub.launch_attempted is False
    print("  [PASS] stub mode is not treated as real execution readiness")

    print("\n=== 3) Valid fake script launches with no engineering input ===")
    probe = _write_probe_script(app_dir / "fake" / "probe", exit_code=0)
    work_dir = app_dir / "dry_run_work"
    selected = _selection(probe, app_dir, working_dir=work_dir)
    assert selected.ok is True
    dry = check_iitpave_dry_run_readiness(
        selected,
        IITPaveDryRunConfig(probe_timeout_sec=3.0),
    )
    assert dry.ok is True
    assert dry.launch_attempted is True
    assert dry.launched is True
    assert dry.returncode == 0
    assert dry.command == (str(probe),)
    assert Path(dry.working_dir) == work_dir
    assert "NON_ENGINEERING_DRY_RUN_PROBE" in dry.stdout_preview
    assert "shell=False" in " ".join(i.message for i in dry.issues)
    assert dry.as_dict()["selection"]["runner_source"] == IITPAVE_RUNNER_EXTERNAL
    print("  [PASS] launch probe records command, working dir, return code")

    print("\n=== 4) Non-zero dry-run exit is warning, not parsed output ===")
    nonzero = _write_probe_script(app_dir / "fake" / "nonzero", exit_code=7)
    nonzero_selected = _selection(nonzero, app_dir)
    nonzero_result = check_iitpave_dry_run_readiness(nonzero_selected)
    assert nonzero_result.ok is True
    assert nonzero_result.has_warnings is True
    assert nonzero_result.returncode == 7
    assert any("no engineering output was parsed" in i.message for i in nonzero_result.issues)
    print("  [PASS] non-zero launch is preserved as readiness warning")

    print("\n=== 5) Launch failure is captured safely ===")
    bad = _write_bad_executable(app_dir / "fake" / "bad.exe")
    bad_selected = _selection(bad, app_dir)
    assert bad_selected.ok is True
    bad_result = check_iitpave_dry_run_readiness(bad_selected)
    assert bad_result.blocked is True
    assert bad_result.launch_attempted is True
    assert bad_result.launched is False
    assert "launch failed safely" in bad_result.blocked_reason
    print("  [PASS] OS launch error becomes blocked dry-run result")

    print("\n=== 6) Launch timeout is bounded and explicit ===")
    slow = _write_probe_script(app_dir / "fake" / "slow", sleep=True)
    slow_selected = _selection(slow, app_dir)
    timeout_result = check_iitpave_dry_run_readiness(
        slow_selected,
        IITPaveDryRunConfig(probe_timeout_sec=0.2),
    )
    assert timeout_result.blocked is True
    assert timeout_result.launch_attempted is True
    assert timeout_result.launched is True
    assert "timed out" in timeout_result.blocked_reason
    print("  [PASS] timeout is captured without hanging the workflow")

    print("\n=== 7) Probe can be disabled for configuration-only readiness ===")
    skipped = check_iitpave_dry_run_readiness(
        selected,
        IITPaveDryRunConfig(launch_probe=False),
    )
    assert skipped.ok is True
    assert skipped.launch_attempted is False
    assert skipped.launched is False
    assert any("skipped" in i.message for i in skipped.issues)
    print("  [PASS] command and working directory can be validated without launch")

    print("\nPHASE 24 IITPAVE DRY-RUN SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
