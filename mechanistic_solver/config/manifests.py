"""Release package manifests, dependencies listing, and code module inventory."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mechanistic_solver.config.production import VERSION, BUILD_NUMBER, COMMIT_HASH, BUILD_TIMESTAMP


# Complete list of code modules in the release
MODULES: Sequence[str] = [
    "mechanistic_solver.core",
    "mechanistic_solver.core.cache",
    "mechanistic_solver.core.profiler",
    "mechanistic_solver.core.models",
    "mechanistic_solver.solver",
    "mechanistic_solver.solver.engine",
    "mechanistic_solver.solver.kernels.multilayer_elastic",
    "mechanistic_solver.solver.integration.hankel_integrator",
    "mechanistic_solver.solver.matrix.transfer_matrix",
    "mechanistic_solver.design",
    "mechanistic_solver.design.irc37_engine",
    "mechanistic_solver.design.fatigue",
    "mechanistic_solver.design.rutting",
    "mechanistic_solver.design.adequacy",
    "mechanistic_solver.design.optimization",
    "mechanistic_solver.optimization.batch_solver",
    "mechanistic_solver.optimization.parallel",
    "mechanistic_solver.licensing.license_manager"
]


# Verified project dependencies
DEPENDENCIES: Mapping[str, str] = {
    "python": ">=3.9",
    "numpy": ">=1.20.0",
    "scipy": ">=1.7.0",
    "pytest": ">=7.0.0"
}


def generate_package_manifest() -> Mapping[str, Any]:
    """Generate a dictionary containing the packaging metadata."""
    return {
        "version": VERSION,
        "build_number": BUILD_NUMBER,
        "commit_hash": COMMIT_HASH,
        "build_timestamp": BUILD_TIMESTAMP,
        "target_os": "Windows",
        "python_runtime": "python-3.14",
        "modules_inventory": list(MODULES),
        "dependencies_manifest": dict(DEPENDENCIES)
    }
