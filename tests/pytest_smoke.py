"""Phase-16 pytest aggregator.

Wraps every standalone ``_smoke_phase*.py`` runner AND the Phase-16
validation harness into pytest cases so a single ``pytest
tests/pytest_smoke.py`` invocation gives a one-line CI verdict.

Each smoke / sample is its own parametrized case, so a failure points at
exactly which corpus or which phase-smoke broke. Individual smokes
remain runnable directly via ``python -m tests._smoke_phaseNN_*`` —
this module only adds an aggregation layer.

Existing test_excel_parity stays separate (already pytest-native and
collected automatically by pytest's discovery).
"""
from __future__ import annotations

import importlib

import pytest

from app.data.sample_projects import list_samples
from tests import validation_harness


# ---------------------------------------------------------------------------
# Phase smoke modules — each exposes a ``main()`` callable returning 0 on PASS.
# ---------------------------------------------------------------------------

PHASE_SMOKES: tuple[str, ...] = (
    "tests._smoke_maintenance",
    "tests._smoke_phase6",
    "tests._smoke_phase7",
    "tests._smoke_phase8",
    "tests._smoke_phase9_stabilization",
    "tests._smoke_phase10_condition",
    "tests._smoke_phase11_image",
    "tests._smoke_phase12_rehab",
    "tests._smoke_phase13_iitpave",
    "tests._smoke_phase14_mechanistic_validation",
    "tests._smoke_phase15_mech_report",
    "tests._smoke_phase15_rehab_report",
    "tests._smoke_phase15_structural_modern",
    "tests._smoke_phase15_persistence",
)


@pytest.mark.parametrize("module_name", PHASE_SMOKES)
def test_phase_smoke(module_name: str) -> None:
    """Run one phase smoke runner and assert its main() returns 0.

    The smoke runners print their own per-section PASS lines; here we
    only enforce the overall exit code so pytest output stays compact.
    """
    mod = importlib.import_module(module_name)
    rc = mod.main() if hasattr(mod, "main") else 0
    assert rc == 0, f"{module_name}.main() returned {rc!r}"


# ---------------------------------------------------------------------------
# Phase-16 validation harness — one pytest case per sample project.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sample_name", list_samples())
def test_validation_sample(sample_name: str) -> None:
    """Run one canonical sample through the full pipeline + golden check."""
    validation_harness.validate_sample(sample_name)
