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
