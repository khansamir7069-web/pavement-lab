from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPAVE_SOURCE_EXTERNAL,
    IITPaveRunnerConfig,
    StructuralInput,
    compute_structural_design,
    parse_iitpave_output,
    run_structural_iitpave_mechanistic_workflow,
)


IITPAVE_TABLE = """IITPAVE OUTPUT
Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR
200 0 0.35 0.11 0.09 0 0 -0.000050 0.000120 0.000110
680L 0 0.04 0.01 0.01 0 0 -0.000220 -0.000030 -0.000020
"""


def test_external_iitpave_table_parser_extracts_microstrain() -> None:
    result = parse_iitpave_output(IITPAVE_TABLE, source=IITPAVE_SOURCE_EXTERNAL)

    assert result.is_placeholder is False
    assert len(result.point_results) == 2
    assert result.point_results[0].epsilon_t_microstrain == 120.0
    assert result.point_results[1].epsilon_z_microstrain == -220.0


def test_structural_workflow_reports_actionable_missing_exe_diagnostic() -> None:
    structural = compute_structural_design(StructuralInput())
    missing = Path(tempfile.mkdtemp()) / "missing_IITPAVE.exe"

    workflow = run_structural_iitpave_mechanistic_workflow(
        structural,
        runner_config=IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(missing),
        ),
    )

    assert workflow.blocked is True
    assert workflow.summary is None
    assert "IITPAVE unavailable" in workflow.structural_result.fatigue_check
    assert str(missing) in workflow.blocked_reason
    assert "Placeholder" not in workflow.structural_result.fatigue_check


def test_structural_workflow_runs_local_executable_and_computes_verdicts() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="iitpave_workflow_test_"))
    if os.name == "nt":
        exe = tmp / "emit_iitpave.cmd"
        exe.write_text(
            "@echo off\n"
            "echo IITPAVE OUTPUT\n"
            "echo Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR\n"
            "echo 200 0 0.35 0.11 0.09 0 0 -0.000050 0.000120 0.000110\n"
            "echo 680L 0 0.04 0.01 0.01 0 0 -0.000220 -0.000030 -0.000020\n",
            encoding="utf-8",
        )
    else:
        exe = tmp / "emit_iitpave"
        exe.write_text(
            "#!/bin/sh\n"
            "cat <<'EOF'\n"
            f"{IITPAVE_TABLE}"
            "EOF\n",
            encoding="utf-8",
        )
        exe.chmod(0o755)

    structural = compute_structural_design(StructuralInput())
    workflow = run_structural_iitpave_mechanistic_workflow(
        structural,
        runner_config=IITPaveRunnerConfig(
            mode=IITPAVE_RUNNER_EXTERNAL,
            configured_executable_path=str(exe),
        ),
    )

    assert workflow.summary is not None
    assert workflow.summary.refused is False
    assert workflow.summary.fatigue.epsilon_t_microstrain == 120.0
    assert workflow.summary.rutting.epsilon_v_microstrain == 220.0
    assert workflow.summary.fatigue.verdict in {"PASS", "FAIL"}
    assert workflow.summary.rutting.verdict in {"PASS", "FAIL"}
    assert "epsilon_t" in workflow.structural_result.fatigue_check
    assert "epsilon_v" in workflow.structural_result.rutting_check
    assert workflow.structural_result.mechanistic_validation is workflow.summary
