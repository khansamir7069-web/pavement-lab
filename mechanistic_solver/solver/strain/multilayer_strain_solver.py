"""Multilayer strain conversion module.

Applies Hooke's law to stress tensors using evaluate_strain.
"""
from __future__ import annotations

from typing import Any, Mapping

from mechanistic_solver.core.models import Layer
from mechanistic_solver.solver.evaluation.strain_evaluator import evaluate_strain


def compute_multilayer_strain(
    stress_result: Mapping[str, Any],
    layer: Layer
) -> dict[str, Any]:
    """Convert stress tensor results to strain tensor components."""
    return evaluate_strain(stress_result, layer)
