from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest
from app.config import USER_DATA_DIR
from app.core import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPAVE_RUNNER_STUB,
    IITPaveRunnerConfig,
    StabilizedInput,
    compute_stabilized_design,
    run_stabilized_iitpave_mechanistic_workflow,
    load_persisted_config,
    save_persisted_config,
    detect_iitpave_version,
    get_last_run_info,
    validate_iitpave_environment,
    IITPaveExternalExeRunner,
)


IITPAVE_OUTPUT_TABLE = """IITPAVE OUTPUT
Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR
200 0 0.35 0.11 0.09 0 0 -0.000050 0.000120 0.000110
680L 0 0.04 0.01 0.01 0 0 -0.000220 -0.000030 -0.000020
"""


def test_installation_manager_config_persistence() -> None:
    # Test saving and loading config
    cfg = IITPaveRunnerConfig(
        mode=IITPAVE_RUNNER_STUB,
        configured_executable_path="dummy_path.exe",
        include_path_search=False,
        timeout_sec=42.0,
    )
    save_persisted_config(cfg)
    loaded = load_persisted_config()
    assert loaded.mode == IITPAVE_RUNNER_STUB
    assert loaded.configured_executable_path == "dummy_path.exe"
    assert loaded.include_path_search is False
    assert loaded.timeout_sec == 42.0


def test_runner_unique_runs_and_log_artifacts() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="iitpave_prod_test_"))
    if os.name == "nt":
        exe = tmp / "mock_iitpave.cmd"
        exe.write_text(
            "@echo off\n"
            "echo IITPAVE OUTPUT\n"
            "echo Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR\n"
            "echo 200 0 0.35 0.11 0.09 0 0 -0.000050 0.000120 0.000110\n"
            "echo 680L 0 0.04 0.01 0.01 0 0 -0.000220 -0.000030 -0.000020\n",
            encoding="utf-8",
        )
    else:
        exe = tmp / "mock_iitpave"
        exe.write_text(
            "#!/bin/sh\n"
            f"echo '{IITPAVE_OUTPUT_TABLE}'\n",
            encoding="utf-8",
        )
        exe.chmod(0o755)

    runner = IITPaveExternalExeRunner(exe_path=exe, timeout_sec=10.0, use_stdin_stdout=True)
    out = runner.run("dummy input text")
    assert "IITPAVE OUTPUT" in out

    # Check that runs folder has the run directory
    runs_dir = USER_DATA_DIR / "iitpave_runs"
    assert runs_dir.is_dir()
    
    # Find the latest run folder
    subdirs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    assert len(subdirs) > 0
    latest_run = subdirs[0]

    # Verify all 5 files are stored
    assert (latest_run / "iitp_inp.dat").is_file()
    assert (latest_run / "iitp_out.dat").is_file()
    assert (latest_run / "stdout.log").is_file()
    assert (latest_run / "stderr.log").is_file()
    assert (latest_run / "run_status.json").is_file()

    # Verify run status fields
    status = json.loads((latest_run / "run_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "success"
    assert status["returncode"] == 0
    assert status["duration_sec"] > 0


def test_stabilized_workflow_mechanistic_verified_mode() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="iitpave_prod_test_"))
    if os.name == "nt":
        exe = tmp / "mock_iitpave.cmd"
        exe.write_text(
            "@echo off\n"
            "echo IITPAVE OUTPUT\n"
            "echo Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR\n"
            "echo 200 0 0.35 0.11 0.09 0 0 -0.000050 0.000120 0.000110\n"
            "echo 680L 0 0.04 0.01 0.01 0 0 -0.000220 -0.000030 -0.000020\n",
            encoding="utf-8",
        )
    else:
        exe = tmp / "mock_iitpave"
        exe.write_text(
            "#!/bin/sh\n"
            f"echo '{IITPAVE_OUTPUT_TABLE}'\n",
            encoding="utf-8",
        )
        exe.chmod(0o755)

    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C1.5/2.0",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        bituminous_thickness_mm=100.0,
        gsb_thickness_mm=150.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
        notes="Test run",
    )
    res = compute_stabilized_design(inp, has_mechanistic_validation=False)

    cfg = IITPaveRunnerConfig(
        mode=IITPAVE_RUNNER_EXTERNAL,
        configured_executable_path=str(exe),
    )
    workflow = run_stabilized_iitpave_mechanistic_workflow(res, runner_config=cfg)
    
    assert workflow.summary is not None
    assert workflow.summary.refused is False
    assert workflow.structural_result.validation_mode == "Mechanistic Verified Mode"
    assert workflow.structural_result.mechanistic_validation is not None


def test_stabilized_workflow_decision_support_mode_on_stub() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C1.5/2.0",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        bituminous_thickness_mm=100.0,
        gsb_thickness_mm=150.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
        notes="Test stub run",
    )
    res = compute_stabilized_design(inp, has_mechanistic_validation=False)

    cfg = IITPaveRunnerConfig(
        mode=IITPAVE_RUNNER_STUB,
    )
    workflow = run_stabilized_iitpave_mechanistic_workflow(res, runner_config=cfg)

    # Stub run returns summary marked is_placeholder=True, which keeps it in Decision Support Mode
    assert workflow.summary is not None
    assert workflow.summary.is_placeholder is True
    assert workflow.structural_result.validation_mode == "Decision Support Mode"


def test_stabilized_workflow_parser_failure_raises_exact_string() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="iitpave_prod_test_"))
    if os.name == "nt":
        exe = tmp / "mock_iitpave.cmd"
        exe.write_text(
            "@echo off\n"
            "echo IITPAVE COMPLETED BUT UNPARSABLE GARBAGE OUTPUT\n",
            encoding="utf-8",
        )
    else:
        exe = tmp / "mock_iitpave"
        exe.write_text(
            "#!/bin/sh\n"
            "echo 'IITPAVE COMPLETED BUT UNPARSABLE GARBAGE OUTPUT'\n",
            encoding="utf-8",
        )
        exe.chmod(0o755)

    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C1.5/2.0",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        bituminous_thickness_mm=100.0,
        gsb_thickness_mm=150.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
        notes="Test parser failure",
    )
    res = compute_stabilized_design(inp, has_mechanistic_validation=False)

    cfg = IITPaveRunnerConfig(
        mode=IITPAVE_RUNNER_EXTERNAL,
        configured_executable_path=str(exe),
    )
    workflow = run_stabilized_iitpave_mechanistic_workflow(res, runner_config=cfg)

    # Execution completed but output contract/parser checks must block it
    assert workflow.blocked is True
    assert workflow.blocked_reason == "IITPAVE execution completed but output verification failed."
    assert workflow.structural_result.validation_mode == "Decision Support Mode"
