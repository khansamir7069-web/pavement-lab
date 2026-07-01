"""Licensing integration and modular tier verification components."""
from __future__ import annotations

from mechanistic_solver.licensing.features import (
    FEATURE_HALFSPACE_SOLVER,
    FEATURE_MULTILAYER_SOLVER,
    FEATURE_PARALLEL_EXECUTION,
    FEATURE_LAYER_OPTIMIZATION,
    FEATURE_PROFILER_REPORT
)
from mechanistic_solver.licensing.license_manager import LicenseManager, LicenseRestrictedError, active_license
