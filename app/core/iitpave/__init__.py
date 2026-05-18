"""Phase-13 IITPAVE integration layer.

Pure-Python scaffolding for mechanistic (elastic-layer) pavement
analysis. The package is intentionally split into four independent
files so each surface can be refined in isolation:

  * ``pavement_structure``  — layered-pavement / load / evaluation-point
                              data structures + adapter.
  * ``input_builder``       — pure text generation from those inputs.
  * ``runner``              — execution abstraction
                              (``IITPaveRunner`` Protocol,
                              ``StubRunner``, ``ExternalExeRunner``).
  * ``parser``              — output-text parser returning
                              ``MechanisticResult``.

V1 ships the stub only; bundling the IITPAVE executable lands with
Phase 17. No UI, no DB, no report wiring in this step — those are
Phase 14 / 15 concerns.
"""
from __future__ import annotations

from .input_builder import (
    INPUT_FORMAT_VERSION,
    build_iitpave_input,
)
from .discovery import (
    DEFAULT_EXE_FILENAME_POSIX,
    DEFAULT_EXE_FILENAME_WIN,
    IITPAVE_EXECUTABLE_ENV_VAR,
    IITPaveEnvironmentIssue,
    IITPaveEnvironmentValidationResult,
    IITPaveExecutableCandidate,
    bundled_iitpave_dir,
    bundled_iitpave_exe_candidates,
    bundled_iitpave_exe_path,
    discover_iitpave_executable,
    validate_iitpave_environment,
)
from .dry_run import (
    IITPaveDryRunConfig,
    IITPaveDryRunResult,
    check_iitpave_dry_run_readiness,
)
from .fixture_intake import (
    DEFAULT_FIXTURE_MANIFEST,
    DEFAULT_OUTPUT_SUFFIXES,
    FIXTURE_STATUS_OPERATOR_PENDING,
    FIXTURE_STATUS_REJECTED,
    FIXTURE_STATUS_UNVERIFIED,
    FIXTURE_STATUS_VERIFIED,
    SUPPORTED_FIXTURE_STATUSES,
    IITPaveFixtureIntakeResult,
    IITPaveFixtureRecord,
    IITPaveParserContractHarnessResult,
    intake_iitpave_fixture_folder,
    intake_iitpave_output_fixture,
    run_iitpave_parser_contract_harness,
)
from .output_contract import (
    IITPAVE_OUTPUT_FORMAT_REAL_PENDING,
    IITPAVE_OUTPUT_FORMAT_STUB,
    IITPAVE_OUTPUT_FORMAT_UNKNOWN,
    IITPAVE_OUTPUT_STATUS_EMPTY,
    IITPAVE_OUTPUT_STATUS_MISSING,
    IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING,
    IITPAVE_OUTPUT_STATUS_STUB_CONTRACT,
    IITPAVE_OUTPUT_STATUS_UNREADABLE,
    IITPAVE_OUTPUT_STATUS_UNSUPPORTED,
    IITPaveOutputContractResult,
    inspect_iitpave_output_contract,
)
from .parser import (
    is_known_stub_output,
    parse_iitpave_output,
)
from .pavement_structure import (
    REFERENCES,
    EvaluationPoint,
    LoadConfig,
    PavementLayer,
    PavementStructure,
    default_evaluation_points,
    from_structural_layers,
)
from .results import (
    PLACEHOLDER_NOTE,
    MechanisticResult,
    PointResult,
)
from .runner import (
    SOURCE_EXTERNAL,
    SOURCE_STUB,
    STUB_OUTPUT_VERSION,
    ExternalExeRunner,
    IITPaveRunner,
    StubRunner,
    default_iitpave_exe_path,
)
from .runner_config import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPAVE_RUNNER_STUB,
    SUPPORTED_IITPAVE_RUNNER_MODES,
    IITPaveRunnerConfig,
    IITPaveRunnerSelectionResult,
    iitpave_runner_config_from_mapping,
    select_iitpave_runner,
)

__all__ = [
    # structure / load / points
    "PavementLayer",
    "PavementStructure",
    "LoadConfig",
    "EvaluationPoint",
    "default_evaluation_points",
    "from_structural_layers",
    "REFERENCES",
    # input / output
    "build_iitpave_input",
    "parse_iitpave_output",
    "is_known_stub_output",
    "INPUT_FORMAT_VERSION",
    "STUB_OUTPUT_VERSION",
    # discovery / environment validation
    "DEFAULT_EXE_FILENAME_POSIX",
    "DEFAULT_EXE_FILENAME_WIN",
    "IITPAVE_EXECUTABLE_ENV_VAR",
    "IITPaveEnvironmentIssue",
    "IITPaveEnvironmentValidationResult",
    "IITPaveExecutableCandidate",
    "bundled_iitpave_dir",
    "bundled_iitpave_exe_candidates",
    "bundled_iitpave_exe_path",
    "discover_iitpave_executable",
    "validate_iitpave_environment",
    # dry-run readiness
    "IITPaveDryRunConfig",
    "IITPaveDryRunResult",
    "check_iitpave_dry_run_readiness",
    # fixture intake / parser contract harness
    "DEFAULT_FIXTURE_MANIFEST",
    "DEFAULT_OUTPUT_SUFFIXES",
    "FIXTURE_STATUS_OPERATOR_PENDING",
    "FIXTURE_STATUS_REJECTED",
    "FIXTURE_STATUS_UNVERIFIED",
    "FIXTURE_STATUS_VERIFIED",
    "SUPPORTED_FIXTURE_STATUSES",
    "IITPaveFixtureIntakeResult",
    "IITPaveFixtureRecord",
    "IITPaveParserContractHarnessResult",
    "intake_iitpave_fixture_folder",
    "intake_iitpave_output_fixture",
    "run_iitpave_parser_contract_harness",
    # output contract / parser guardrails
    "IITPAVE_OUTPUT_FORMAT_REAL_PENDING",
    "IITPAVE_OUTPUT_FORMAT_STUB",
    "IITPAVE_OUTPUT_FORMAT_UNKNOWN",
    "IITPAVE_OUTPUT_STATUS_EMPTY",
    "IITPAVE_OUTPUT_STATUS_MISSING",
    "IITPAVE_OUTPUT_STATUS_REAL_CONTRACT_PENDING",
    "IITPAVE_OUTPUT_STATUS_STUB_CONTRACT",
    "IITPAVE_OUTPUT_STATUS_UNREADABLE",
    "IITPAVE_OUTPUT_STATUS_UNSUPPORTED",
    "IITPaveOutputContractResult",
    "inspect_iitpave_output_contract",
    # results
    "PointResult",
    "MechanisticResult",
    "PLACEHOLDER_NOTE",
    # runners
    "IITPaveRunner",
    "StubRunner",
    "ExternalExeRunner",
    "default_iitpave_exe_path",
    "SOURCE_STUB",
    "SOURCE_EXTERNAL",
    # runner selection
    "IITPAVE_RUNNER_EXTERNAL",
    "IITPAVE_RUNNER_STUB",
    "SUPPORTED_IITPAVE_RUNNER_MODES",
    "IITPaveRunnerConfig",
    "IITPaveRunnerSelectionResult",
    "iitpave_runner_config_from_mapping",
    "select_iitpave_runner",
]
