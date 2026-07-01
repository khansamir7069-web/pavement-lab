"""License manager controlling feature availability based on active product tier."""
from __future__ import annotations

import os
from typing import Any

from mechanistic_solver.licensing.features import TIERS


class LicenseRestrictedError(Exception):
    """Custom exception raised when a feature is blocked by the active licensing tier."""
    pass


class LicenseManager:
    """Modular local licensing manager verifying tier permissions and keys."""

    def __init__(self, tier: str | None = None) -> None:
        # Default to Enterprise mode to preserve backward compatibility and test runs
        self._tier = tier or os.environ.get("ROADX_LICENSE_TIER", "Enterprise")
        if self._tier not in TIERS:
            self._tier = "Enterprise"

    def get_tier(self) -> str:
        """Get the active licensing tier name."""
        return self._tier

    def set_tier(self, tier: str) -> None:
        """Dynamically set the active tier (primarily for testing and profile shifting)."""
        if tier in TIERS:
            self._tier = tier
        else:
            raise ValueError(f"Invalid license tier: {tier}")

    def is_feature_allowed(self, feature: str) -> bool:
        """Check if a specific feature is enabled for the active tier."""
        tier_features = TIERS.get(self._tier, {})
        return tier_features.get(feature, False)

    def check_feature(self, feature: str) -> None:
        """Enforce license restriction by raising an error if the feature is disabled."""
        if not self.is_feature_allowed(feature):
            raise LicenseRestrictedError(
                f"Feature '{feature}' is disabled in the active '{self._tier}' license tier. "
                f"Please upgrade to Professional or Enterprise Edition to unlock this feature."
            )

    def apply_license_key(self, key: str) -> bool:
        """Apply a license key file or string to select the corresponding tier locally."""
        clean_key = key.strip()
        if "ROADX-COMM-KEY" in clean_key:
            self.set_tier("Community")
            return True
        elif "ROADX-PRO-KEY" in clean_key:
            self.set_tier("Professional")
            return True
        elif "ROADX-ENT-KEY" in clean_key:
            self.set_tier("Enterprise")
            return True
        return False


# Singleton active license manager instance
active_license = LicenseManager()
