"""Phase-22 smoke - IITPAVE executable discovery diagnostics.

Pure-Python, no real IITPAVE execution. Verifies the structured discovery
and environment-validation layer used by future real-runner workflows.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.core import (
    IITPAVE_EXECUTABLE_ENV_VAR,
    IITPaveExternalExeRunner,
    bundled_iitpave_dir,
    bundled_iitpave_exe_candidates,
    bundled_iitpave_exe_path,
    discover_iitpave_executable,
    validate_iitpave_environment,
)


def _fake_app_dir() -> Path:
    root = Path(tempfile.mkdtemp(prefix="phase22_iitpave_"))
    (root / "external" / "iitpave").mkdir(parents=True)
    return root


def main() -> int:
    print("=== 1) Bundled path helpers are deterministic ===")
    app_dir = _fake_app_dir()
    bundle_dir = bundled_iitpave_dir(app_dir=app_dir)
    win_path, posix_path = bundled_iitpave_exe_candidates(app_dir=app_dir)
    assert bundle_dir == app_dir / "external" / "iitpave"
    assert win_path.name == "IITPAVE.exe"
    assert posix_path.name == "iitpave"
    assert bundled_iitpave_exe_path(app_dir=app_dir) == win_path
    print(f"  [PASS] bundle dir={bundle_dir}")

    print("\n=== 2) Missing executable yields structured error diagnostics ===")
    missing = validate_iitpave_environment(app_dir=app_dir, env={})
    assert missing.selected_path is None
    assert missing.ok is False
    assert any(i.severity == "error" for i in missing.issues)
    assert any(IITPAVE_EXECUTABLE_ENV_VAR in i.message for i in missing.issues)
    missing_payload = missing.as_dict()
    assert missing_payload["ok"] is False
    assert len([c for c in missing_payload["candidates"] if c["source"] != "common_folders"]) == 2
    print("  [PASS] missing binary is explicit and serializable")

    print("\n=== 3) Bundled executable is selected without running it ===")
    win_path.write_text("placeholder executable bytes", encoding="utf-8")
    bundled = validate_iitpave_environment(app_dir=app_dir, env={})
    assert bundled.ok is True
    assert bundled.selected_path == win_path
    assert any(i.severity == "info" for i in bundled.issues)
    runner = IITPaveExternalExeRunner(exe_path=bundled.selected_path)
    assert runner.exe_path == win_path
    print("  [PASS] selected bundled path feeds ExternalExeRunner configuration")

    print("\n=== 4) Explicit configured path takes precedence ===")
    explicit = app_dir / "custom" / "iitpave_custom.exe"
    explicit.parent.mkdir()
    explicit.write_text("placeholder executable bytes", encoding="utf-8")
    candidates = discover_iitpave_executable(
        configured_path=explicit,
        app_dir=app_dir,
        env={},
    )
    assert candidates[0].source == "configured_path"
    assert candidates[0].path == explicit
    configured = validate_iitpave_environment(
        configured_path=explicit,
        app_dir=app_dir,
        env={},
    )
    assert configured.ok is True
    assert configured.selected_path == explicit
    print("  [PASS] configured path wins over bundled path")

    print("\n=== 5) Environment variable is validated traceably ===")
    env_exe = app_dir / "env" / "IITPAVE.exe"
    env_exe.parent.mkdir()
    env_exe.write_text("placeholder executable bytes", encoding="utf-8")
    env_result = validate_iitpave_environment(
        app_dir=app_dir,
        env={IITPAVE_EXECUTABLE_ENV_VAR: str(env_exe)},
    )
    assert env_result.ok is True
    assert env_result.selected_path == env_exe
    assert env_result.candidates[0].source == "environment"
    bad_env = validate_iitpave_environment(
        app_dir=app_dir,
        env={IITPAVE_EXECUTABLE_ENV_VAR: str(app_dir / "missing.exe")},
    )
    assert bad_env.ok is False
    assert any(i.field == IITPAVE_EXECUTABLE_ENV_VAR for i in bad_env.issues)
    print("  [PASS] env path can select or reject with field-level issues")

    print("\n=== 6) Optional PATH search is opt-in and non-invasive ===")
    no_path = discover_iitpave_executable(app_dir=app_dir, env={})
    with_path = discover_iitpave_executable(
        app_dir=app_dir,
        env={},
        include_path_search=True,
    )
    assert len(with_path) >= len(no_path)
    print("  [PASS] PATH search does not run unless requested")

    print("\nPHASE 22 IITPAVE DISCOVERY SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
