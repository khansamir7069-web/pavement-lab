"""Production configuration manager and release metadata declarations."""
from __future__ import annotations

import time
from typing import Any, Mapping

from mechanistic_solver.config.profiles import SolverProfile, load_profile, validate_profile


VERSION: str = "2.2.0"
BUILD_NUMBER: str = "1042"
RELEASE_TIER: str = "Enterprise"
COMMIT_HASH: str = "8ac5b6a9e1"
BUILD_TIMESTAMP: str = "2026-06-30T14:38:00Z"


class ProductionConfigurationManager:
    """Consolidated configuration manager for active profile loading and version metadata."""

    def __init__(self, profile_name: str | None = None) -> None:
        self.profile: SolverProfile = load_profile(profile_name)
        
    def get_version_info(self) -> Mapping[str, str]:
        """Fetch package metadata for manifest files and release verification."""
        return {
            "version": VERSION,
            "build_number": BUILD_NUMBER,
            "release_tier": RELEASE_TIER,
            "commit_hash": COMMIT_HASH,
            "build_timestamp": BUILD_TIMESTAMP
        }

    def validate_current_setup(self) -> bool:
        """Confirm that the loaded active profile conforms to stability requirements."""
        return validate_profile(self.profile)


# Singleton instance for application usage
active_config = ProductionConfigurationManager()
