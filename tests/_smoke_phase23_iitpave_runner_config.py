"""Phase-23 smoke - safe IITPAVE runner selection/configuration."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from app.core import (
    IITPAVE_EXECUTABLE_ENV_VAR,
    IITPAVE_RUNNER_EXTERNAL,
    IITPAVE_RUNNER_STUB,
    IITPaveExternalExeRunner,
    IITPaveRunnerConfig,
    IITPaveStubRunner,
    iitpave_runner_config_from_mapping,
    select_iitpave_runner,
)


def _fake_app_dir() -> Path:
    root = Path(tempfile.mkdtemp(prefix="phase23_iitpave_"))
    (root / "external" / "iitpave").mkdir(parents=True)
    return root


def _write_fake_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("operator supplied binary placeholder for config tests", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    return path


def main() -> int:
    print("=== 1) Default config preserves stub runner behavior ===")
    app_dir = _fake_app_dir()
    default = select_iitpave_runner(app_dir=app_dir, env={})
    assert default.ok is True
    assert default.blocked is False
    assert default.runner_source == IITPAVE_RUNNER_STUB
    assert isinstance(default.runner, IITPaveStubRunner)
    assert default.selected_path is None
    assert default.as_dict()["config"]["mode"] == IITPAVE_RUNNER_STUB
    print("  [PASS] no executable required for stub mode")

    print("\n=== 2) External mode blocks missing executable ===")
    missing = select_iitpave_runner(
        IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL),
        app_dir=app_dir,
        env={},
    )
    assert missing.ok is False
    assert missing.blocked is True
    assert missing.runner is None
    assert "No IITPAVE executable" in missing.blocked_reason
    assert missing.as_dict()["blocked"] is True
    print("  [PASS] missing executable returns blocked result")

    print("\n=== 3) External mode blocks invalid and non-file paths ===")
    invalid = select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path="\0not-a-valid-path",
        ),
        app_dir=app_dir,
        env={},
    )
    assert invalid.blocked is True
    assert any("invalid or inaccessible" in i.message for i in invalid.issues)

    non_file = select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(app_dir / "external" / "iitpave"),
        ),
        app_dir=app_dir,
        env={},
    )
    assert non_file.blocked is True
    assert any("not a file" in i.message for i in non_file.issues)
    print("  [PASS] invalid path and directory path are rejected")

    print("\n=== 4) User-configured path selects ExternalExeRunner without executing ===")
    configured_path = _write_fake_exe(app_dir / "custom" / "IITPAVE.exe")
    configured = select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(configured_path),
            timeout_sec=17.0,
            use_stdin_stdout=False,
        ),
        app_dir=app_dir,
        env={},
    )
    assert configured.ok is True
    assert configured.blocked is False
    assert isinstance(configured.runner, IITPaveExternalExeRunner)
    assert configured.selected_path == configured_path
    assert configured.selected_candidate_source == "configured_path"
    assert configured.runner.timeout_sec == 17.0
    assert configured.runner.use_stdin_stdout is False
    print("  [PASS] valid configured executable creates external runner only")

    print("\n=== 5) Environment and bundled paths are selected by discovery order ===")
    env_path = _write_fake_exe(app_dir / "env" / "IITPAVE.exe")
    bundled_path = _write_fake_exe(app_dir / "external" / "iitpave" / "IITPAVE.exe")
    env_selected = select_iitpave_runner(
        IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL),
        app_dir=app_dir,
        env={IITPAVE_EXECUTABLE_ENV_VAR: str(env_path)},
    )
    assert env_selected.ok is True
    assert env_selected.selected_path == env_path
    assert env_selected.selected_candidate_source == "environment"

    bundled_selected = select_iitpave_runner(
        IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL),
        app_dir=app_dir,
        env={},
    )
    assert bundled_selected.ok is True
    assert bundled_selected.selected_path == bundled_path
    assert bundled_selected.selected_candidate_source == "bundled"
    print("  [PASS] environment path precedes bundled path; bundled works alone")

    print("\n=== 6) PATH discovery is opt-in ===")
    path_app_dir = _fake_app_dir()
    path_bin = _write_fake_exe(path_app_dir / "pathbin" / "IITPAVE.exe")
    no_path = select_iitpave_runner(
        IITPaveRunnerConfig(mode=IITPAVE_RUNNER_EXTERNAL),
        app_dir=path_app_dir,
        env={"PATH": str(path_bin.parent)},
    )
    assert no_path.blocked is True
    with_path = select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            include_path_search=True,
        ),
        app_dir=path_app_dir,
        env={"PATH": str(path_bin.parent)},
    )
    assert with_path.ok is True
    assert with_path.selected_path == path_bin
    assert with_path.selected_candidate_source == "path"
    assert with_path.as_dict()["environment"]["issues"]
    print("  [PASS] PATH executable is ignored unless include_path_search=True")

    print("\n=== 7) Empty executable file is treated as execution risk ===")
    empty = app_dir / "empty" / "IITPAVE.exe"
    empty.parent.mkdir()
    empty.write_bytes(b"")
    empty_result = select_iitpave_runner(
        IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(empty),
        ),
        app_dir=app_dir,
        env={},
    )
    assert empty_result.blocked is True
    assert any("empty" in i.message for i in empty_result.issues)
    print("  [PASS] detectable execution-risk blocks real runner")

    print("\n=== 8) Mapping loader is audit-friendly and backward-compatible ===")
    cfg = iitpave_runner_config_from_mapping({
        "mode": IITPAVE_RUNNER_EXTERNAL,
        "executable_path": str(configured_path),
        "include_path_search": True,
        "timeout_sec": 12,
    })
    assert cfg.mode == IITPAVE_RUNNER_EXTERNAL
    assert cfg.configured_executable_path == str(configured_path)
    assert cfg.as_dict()["include_path_search"] is True
    assert cfg.as_dict()["timeout_sec"] == 12.0
    print("  [PASS] config mapping supports executable_path alias + serialization")

    print("\nPHASE 23 IITPAVE RUNNER CONFIG SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
