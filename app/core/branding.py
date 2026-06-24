"""Consultant Branding & Profile Settings.

Handles loading, saving, and querying local consultant company settings
used for report cover pages and signature blocks.
"""
from __future__ import annotations

import json
from pathlib import Path
from app.config import USER_DATA_DIR

BRANDING_FILE = USER_DATA_DIR / "branding_profile.json"


def get_branding_profile() -> dict:
    """Load the locally saved branding profile. Returns default dict if not found/invalid."""
    defaults = {
        "company_name": "",
        "logo_path": "",
        "address": "",
        "contact": "",
        "engineer_name": "",
        "registration_number": ""
    }
    if BRANDING_FILE.is_file():
        try:
            with open(BRANDING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Merge keys to ensure defaults exist
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                    return data
        except Exception:
            pass
    return defaults


def save_branding_profile(profile: dict) -> None:
    """Save the branding profile settings to local file."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_profile = {
        "company_name": str(profile.get("company_name", "")),
        "logo_path": str(profile.get("logo_path", "")),
        "address": str(profile.get("address", "")),
        "contact": str(profile.get("contact", "")),
        "engineer_name": str(profile.get("engineer_name", "")),
        "registration_number": str(profile.get("registration_number", ""))
    }
    with open(BRANDING_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_profile, f, indent=4, ensure_ascii=False)
