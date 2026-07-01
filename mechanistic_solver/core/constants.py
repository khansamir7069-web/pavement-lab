"""Centralized engineering constants for the mechanistic solver.

All numerical thresholds, physical constants, and precision limits are defined
here to eliminate magic numbers from the codebase.
"""
from __future__ import annotations

import math

# Physical constants
GRAVITY_M_S2: float = 9.80665
STANDARD_ATM_PRESSURE_KPA: float = 101.325
PI: float = math.pi

# Solver Defaults & Tolerances
DEFAULT_POISSON_RATIO: float = 0.35
DEFAULT_TEMPERATURE_CELSIUS: float = 35.0
MAX_SUPPORTED_LAYERS: int = 15
DEFAULT_INTEGRATION_TOLERANCE: float = 1e-6
NUMERICAL_PRECISION_LIMIT: float = 1e-12

# Smallest radial (Hankel) parameter m treated as the analytic m->0 limit.
# response_functions clamps integrand evaluations to this floor, and the
# boundary-condition assembler switches to the closed-form limit branch at the
# same threshold so the two are mutually consistent (no singular artefact).
SMALL_RADIAL_PARAMETER: float = 1e-9

# Engineering limits & validation boundaries
MIN_POISSON_RATIO: float = 0.0
MAX_POISSON_RATIO: float = 0.5

MIN_MODULUS_MPA: float = 0.1
MAX_MODULUS_MPA: float = 100000.0

MIN_THICKNESS_MM: float = 1.0
MAX_THICKNESS_MM: float = 10000.0

MIN_DENSITY_KG_M3: float = 100.0
MAX_DENSITY_KG_M3: float = 5000.0

# Centralized error code keys
ERROR_CODE_THICKNESS: str = "ERR_LIMIT_THICKNESS"
ERROR_CODE_LIMIT_THICKNESS: str = "ERR_LIMIT_THICKNESS"
ERROR_CODE_MODULUS: str = "ERR_LIMIT_MODULUS"
ERROR_CODE_LIMIT_MODULUS: str = "ERR_LIMIT_MODULUS"
ERROR_CODE_POISSON: str = "ERR_LIMIT_POISSON"
ERROR_CODE_LIMIT_POISSON: str = "ERR_LIMIT_POISSON"
ERROR_CODE_DENSITY: str = "ERR_LIMIT_DENSITY"
ERROR_CODE_LIMIT_DENSITY: str = "ERR_LIMIT_DENSITY"
ERROR_CODE_SUBGRADE: str = "ERR_SUBGRADE_INFINITE"
ERROR_CODE_LAYER_ORDER: str = "ERR_LAYER_ORDER"
ERROR_CODE_OVERLAP: str = "ERR_LAYER_OVERLAP"
ERROR_CODE_DUPLICATE: str = "ERR_DUPLICATE_LAYER"
ERROR_CODE_MISSING_PROP: str = "ERR_MISSING_PROPERTY"
