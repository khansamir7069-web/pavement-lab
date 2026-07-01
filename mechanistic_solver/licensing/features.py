"""Licensing features mappings for Community, Professional, and Enterprise editions."""
from __future__ import annotations

from typing import Mapping


# Feature codes
FEATURE_HALFSPACE_SOLVER = "halfspace_solver"
FEATURE_MULTILAYER_SOLVER = "multilayer_solver"
FEATURE_PARALLEL_EXECUTION = "parallel_execution"
FEATURE_LAYER_OPTIMIZATION = "layer_optimization"
FEATURE_PROFILER_REPORT = "profiler_report"


# Tier capability mappings
TIERS: Mapping[str, Mapping[str, bool]] = {
    "Community": {
        FEATURE_HALFSPACE_SOLVER: True,
        FEATURE_MULTILAYER_SOLVER: False,
        FEATURE_PARALLEL_EXECUTION: False,
        FEATURE_LAYER_OPTIMIZATION: False,
        FEATURE_PROFILER_REPORT: False
    },
    "Professional": {
        FEATURE_HALFSPACE_SOLVER: True,
        FEATURE_MULTILAYER_SOLVER: True,
        FEATURE_PARALLEL_EXECUTION: False,
        FEATURE_LAYER_OPTIMIZATION: True,
        FEATURE_PROFILER_REPORT: False
    },
    "Enterprise": {
        FEATURE_HALFSPACE_SOLVER: True,
        FEATURE_MULTILAYER_SOLVER: True,
        FEATURE_PARALLEL_EXECUTION: True,
        FEATURE_LAYER_OPTIMIZATION: True,
        FEATURE_PROFILER_REPORT: True
    }
}
