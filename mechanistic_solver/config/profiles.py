"""Configuration profiles definition for dev, prod, benchmark, and debug environments."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SolverProfile:
    """Structure defining runtime settings for a specific deployment environment."""
    name: str
    tolerance: float
    max_limit: int
    cache_max_size: int
    log_level: str
    condition_checking: bool
    description: str


# Preset profiles configuration
PROFILES: Mapping[str, SolverProfile] = {
    "development": SolverProfile(
        name="development",
        tolerance=1e-5,
        max_limit=1000,
        cache_max_size=10000,
        log_level="DEBUG",
        condition_checking=True,
        description="Profile optimized for rapid local development, testing, and troubleshooting."
    ),
    "production": SolverProfile(
        name="production",
        tolerance=1e-6,
        max_limit=5000,
        cache_max_size=50000,
        log_level="INFO",
        condition_checking=False,
        description="Standard production profile providing high precision and optimal cache memory usage."
    ),
    "benchmark": SolverProfile(
        name="benchmark",
        tolerance=1e-8,
        max_limit=10000,
        cache_max_size=100000,
        log_level="INFO",
        condition_checking=True,
        description="High-precision validation profile matching absolute IITPAVE parity precision levels."
    ),
    "debug": SolverProfile(
        name="debug",
        tolerance=1e-4,
        max_limit=500,
        cache_max_size=1000,
        log_level="DEBUG",
        condition_checking=True,
        description="Low-precision debug profile with full matrix condition reporting enabled."
    )
}


def load_profile(name: str | None = None) -> SolverProfile:
    """Load a solver profile by name, falling back to environment override or default."""
    profile_name = name or os.environ.get("ROADX_PROFILE", "production")
    profile_name = profile_name.lower().strip()
    
    if profile_name not in PROFILES:
        profile_name = "production"
        
    p = PROFILES[profile_name]
    
    # Environment overrides support
    tol = float(os.environ.get("ROADX_TOLERANCE", p.tolerance))
    limit = int(os.environ.get("ROADX_MAX_LIMIT", p.max_limit))
    cache_sz = int(os.environ.get("ROADX_CACHE_SIZE", p.cache_max_size))
    
    return SolverProfile(
        name=p.name,
        tolerance=tol,
        max_limit=limit,
        cache_max_size=cache_sz,
        log_level=p.log_level,
        condition_checking=p.condition_checking,
        description=p.description
    )


def validate_profile(profile: SolverProfile) -> bool:
    """Assert that a loaded profile contains valid bounds to prevent mathematical crashes."""
    if profile.tolerance <= 0.0 or profile.tolerance > 0.1:
        return False
    if profile.max_limit < 10 or profile.max_limit > 100000:
        return False
    if profile.cache_max_size < 0:
        return False
    return True
