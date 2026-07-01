"""Configuration and release packaging modules."""
from __future__ import annotations

from mechanistic_solver.config.profiles import SolverProfile, load_profile, validate_profile
from mechanistic_solver.config.production import VERSION, active_config
from mechanistic_solver.config.manifests import generate_package_manifest
