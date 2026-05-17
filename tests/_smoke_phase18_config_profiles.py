"""Phase-18 smoke - centralized configuration/profile infrastructure.

Pure-Python, no UI and no DB. Verifies that application profiles resolve
through a single core model, invalid inputs fall back safely, schema
metadata is version-aware, and report rendering remains opt-in.
"""
from __future__ import annotations

import sys

from app import __version__
from app.core import (
    CONFIG_SCHEMA_VERSION,
    PROFILE_CONSULTANCY,
    PROFILE_DEFAULT,
    PROFILE_DEMO,
    PROFILE_LAB,
    SUPPORTED_PROFILE_KEYS,
    config_report_rows,
    list_application_profiles,
    load_application_config,
    resolve_application_config,
    validate_application_config,
    validate_config_payload,
)
from app.reports._docx_common import add_config_metadata, new_portrait_document


def _doc_text(doc) -> str:
    chunks: list[str] = []
    chunks.extend(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                chunks.append(cell.text)
    return "\n".join(chunks)


def main() -> int:
    print("=== 1) Built-in profile registry ===")
    profiles = list_application_profiles()
    keys = tuple(p.key for p in profiles)
    assert keys == SUPPORTED_PROFILE_KEYS
    assert keys == (PROFILE_DEFAULT, PROFILE_LAB, PROFILE_CONSULTANCY, PROFILE_DEMO)
    assert all(p.display_name for p in profiles)
    print(f"  [PASS] profiles={', '.join(keys)}")

    print("\n=== 2) Safe default fallback for invalid profile ===")
    unknown = resolve_application_config("field-office", source="smoke")
    assert unknown.profile.key == PROFILE_DEFAULT
    assert unknown.metadata.requested_profile == "field-office"
    assert unknown.metadata.fallback_used is True
    assert unknown.metadata.validation_issues
    assert validate_application_config(unknown).ok
    print("  [PASS] invalid profile resolved to default with warning metadata")

    print("\n=== 3) Profile-specific metadata defaults ===")
    consultancy = resolve_application_config(PROFILE_CONSULTANCY, source="smoke")
    demo = resolve_application_config(PROFILE_DEMO, source="smoke")
    default = resolve_application_config(source="smoke")
    assert consultancy.report_metadata_enabled is True
    assert demo.profile.sample_data_enabled is True
    assert default.report_metadata_enabled is False
    assert config_report_rows(default) == ()
    assert config_report_rows(consultancy)
    print("  [PASS] profile defaults are centralized and deterministic")

    print("\n=== 4) Version-aware payload validation ===")
    payload = {
        "schema_version": "0.9",
        "profile": "LAB",
        "report_metadata_enabled": True,
    }
    validation = validate_config_payload(payload)
    assert validation.ok
    assert validation.has_warnings
    loaded = load_application_config(payload, source="json")
    assert loaded.profile.key == PROFILE_LAB
    assert loaded.metadata.schema_version == "0.9"
    assert loaded.metadata.app_version == __version__
    assert loaded.report_metadata_enabled is True
    bad_loaded = load_application_config({"profile": "unsupported"}, source="json")
    assert bad_loaded.profile.key == PROFILE_DEFAULT
    assert bad_loaded.metadata.fallback_used is True
    assert validate_application_config(bad_loaded).ok
    malformed = load_application_config("not-a-mapping", source="json")  # type: ignore[arg-type]
    assert malformed.profile.key == PROFILE_DEFAULT
    assert malformed.metadata.fallback_used is True
    assert validate_application_config(malformed).ok
    print(f"  [PASS] schema warning preserved; current schema={CONFIG_SCHEMA_VERSION}")

    print("\n=== 5) Optional report metadata rendering ===")
    doc = new_portrait_document()
    assert add_config_metadata(doc, default) is False
    assert add_config_metadata(doc, consultancy) is True
    text = _doc_text(doc)
    for must_have in (
        "Configuration Metadata",
        "Application Profile",
        "Consultancy (consultancy)",
        "Configuration Schema",
        CONFIG_SCHEMA_VERSION,
    ):
        assert must_have in text, f"missing report metadata text: {must_have!r}"

    forced_doc = new_portrait_document()
    assert add_config_metadata(forced_doc, default, force=True) is True
    assert "Default (default)" in _doc_text(forced_doc)
    print("  [PASS] report metadata is opt-in, with explicit force support")

    print("\nPHASE 18 CONFIG PROFILE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
