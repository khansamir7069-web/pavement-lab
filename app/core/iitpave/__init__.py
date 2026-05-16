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
]
