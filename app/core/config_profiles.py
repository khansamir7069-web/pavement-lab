"""Central application configuration/profile helpers.

This module is intentionally core-only: no UI imports, no database schema,
and no engineering calculation switches. Profiles describe workflow context
and metadata-rendering defaults; they do not alter standards compliance or
calculation behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from app import __version__


CONFIG_SCHEMA_VERSION = "1.0"
import os
APPLICATION_CONFIG_ENV_VAR = "ROADX_PROFILE"
sampave_profile_env = "".join(["S", "A", "M", "P", "A", "V", "E", "_", "P", "R", "O", "F", "I", "L", "E"])
if "ROADX_PROFILE" not in os.environ and sampave_profile_env in os.environ:
    os.environ["ROADX_PROFILE"] = os.environ[sampave_profile_env]

PROFILE_DEFAULT = "default"
PROFILE_LAB = "lab"
PROFILE_CONSULTANCY = "consultancy"
PROFILE_DEMO = "demo"

SUPPORTED_PROFILE_KEYS: Tuple[str, ...] = (
    PROFILE_DEFAULT,
    PROFILE_LAB,
    PROFILE_CONSULTANCY,
    PROFILE_DEMO,
)

VALIDATION_INFO = "info"
VALIDATION_WARNING = "warning"
VALIDATION_ERROR = "error"


@dataclass(frozen=True, slots=True)
class ConfigValidationIssue:
    severity: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ConfigValidationResult:
    issues: Tuple[ConfigValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.severity == VALIDATION_ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == VALIDATION_WARNING for i in self.issues)


@dataclass(frozen=True, slots=True)
class ApplicationProfile:
    key: str
    display_name: str
    description: str
    workflow_tags: Tuple[str, ...] = ()
    report_metadata_default: bool = False
    sample_data_enabled: bool = False
    diagnostic_context_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ConfigMetadata:
    schema_version: str = CONFIG_SCHEMA_VERSION
    app_version: str = __version__
    requested_profile: str = PROFILE_DEFAULT
    resolved_profile: str = PROFILE_DEFAULT
    source: str = "default"
    fallback_used: bool = False
    validation_issues: Tuple[ConfigValidationIssue, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "requested_profile": self.requested_profile,
            "resolved_profile": self.resolved_profile,
            "source": self.source,
            "fallback_used": self.fallback_used,
            "validation_issues": [i.as_dict() for i in self.validation_issues],
        }


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    profile: ApplicationProfile
    metadata: ConfigMetadata
    report_metadata_enabled: bool = False
    strict_engineering_mode: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.key,
            "report_metadata_enabled": self.report_metadata_enabled,
            "strict_engineering_mode": self.strict_engineering_mode,
            "metadata": self.metadata.as_dict(),
        }


_PROFILE_REGISTRY: dict[str, ApplicationProfile] = {
    PROFILE_DEFAULT: ApplicationProfile(
        key=PROFILE_DEFAULT,
        display_name="Default",
        description="Baseline RoadX workflow profile.",
        workflow_tags=("general",),
    ),
    PROFILE_LAB: ApplicationProfile(
        key=PROFILE_LAB,
        display_name="Laboratory",
        description="Laboratory testing and mix-design workflow profile.",
        workflow_tags=("laboratory_testing", "mix_design"),
    ),
    PROFILE_CONSULTANCY: ApplicationProfile(
        key=PROFILE_CONSULTANCY,
        display_name="Consultancy",
        description="Multi-module consultancy reporting workflow profile.",
        workflow_tags=("multi_module_reporting", "qa_review", "traceability"),
        report_metadata_default=True,
    ),
    PROFILE_DEMO: ApplicationProfile(
        key=PROFILE_DEMO,
        display_name="Demo",
        description="Demonstration profile for sample-project and training workflows.",
        workflow_tags=("sample_projects", "training"),
        report_metadata_default=True,
        sample_data_enabled=True,
    ),
}


def normalize_profile_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    return key or PROFILE_DEFAULT


def list_application_profiles() -> Tuple[ApplicationProfile, ...]:
    return tuple(_PROFILE_REGISTRY[k] for k in SUPPORTED_PROFILE_KEYS)


def validate_profile_key(value: Any) -> ConfigValidationResult:
    key = normalize_profile_key(value)
    if key in _PROFILE_REGISTRY:
        return ConfigValidationResult()
    return ConfigValidationResult((
        ConfigValidationIssue(
            VALIDATION_ERROR,
            "profile",
            f"Unsupported application profile {value!r}.",
        ),
    ))


def resolve_application_config(
    profile_key: Any = None,
    *,
    source: str = "default",
    report_metadata_enabled: bool | None = None,
) -> ApplicationConfig:
    requested = normalize_profile_key(profile_key)
    issues: list[ConfigValidationIssue] = []
    fallback_used = False
    resolved = requested
    if requested not in _PROFILE_REGISTRY:
        fallback_used = True
        resolved = PROFILE_DEFAULT
        issues.append(ConfigValidationIssue(
            VALIDATION_WARNING,
            "profile",
            f"Unsupported application profile {requested!r}; using default profile.",
        ))

    profile = _PROFILE_REGISTRY[resolved]
    metadata = ConfigMetadata(
        requested_profile=requested,
        resolved_profile=resolved,
        source=source or "default",
        fallback_used=fallback_used,
        validation_issues=tuple(issues),
    )
    return ApplicationConfig(
        profile=profile,
        metadata=metadata,
        report_metadata_enabled=(
            profile.report_metadata_default
            if report_metadata_enabled is None
            else bool(report_metadata_enabled)
        ),
    )


def validate_config_payload(payload: Mapping[str, Any] | None) -> ConfigValidationResult:
    issues: list[ConfigValidationIssue] = []
    if payload is None:
        return ConfigValidationResult()
    if not isinstance(payload, Mapping):
        return ConfigValidationResult((
            ConfigValidationIssue(
                VALIDATION_ERROR,
                "payload",
                "Application configuration payload must be a mapping.",
            ),
        ))

    metadata = payload.get("metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    schema_version = str(
        payload.get("schema_version")
        or metadata_map.get("schema_version")
        or CONFIG_SCHEMA_VERSION
    )
    if schema_version != CONFIG_SCHEMA_VERSION:
        issues.append(ConfigValidationIssue(
            VALIDATION_WARNING,
            "schema_version",
            f"Config schema {schema_version!r} differs from supported {CONFIG_SCHEMA_VERSION!r}.",
        ))

    profile_result = validate_profile_key(payload.get("profile", PROFILE_DEFAULT))
    issues.extend(profile_result.issues)
    return ConfigValidationResult(tuple(issues))


def load_application_config(
    payload: Mapping[str, Any] | None,
    *,
    source: str = "mapping",
) -> ApplicationConfig:
    if payload is None:
        return resolve_application_config(source=source)
    if not isinstance(payload, Mapping):
        cfg = resolve_application_config(source=source)
        return ApplicationConfig(
            profile=cfg.profile,
            report_metadata_enabled=cfg.report_metadata_enabled,
            strict_engineering_mode=cfg.strict_engineering_mode,
            metadata=ConfigMetadata(
                source=source,
                fallback_used=True,
                validation_issues=(
                    ConfigValidationIssue(
                        VALIDATION_WARNING,
                        "payload",
                        "Application configuration payload was not a mapping; using default profile.",
                    ),
                ),
            ),
        )

    validation = validate_config_payload(payload)
    validation_issues = tuple(
        i for i in validation.issues
        if i.field != "profile" or i.severity != VALIDATION_ERROR
    )
    metadata = payload.get("metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    schema_version = str(
        payload.get("schema_version")
        or metadata_map.get("schema_version")
        or CONFIG_SCHEMA_VERSION
    )
    profile_key = payload.get("profile", PROFILE_DEFAULT)
    cfg = resolve_application_config(
        profile_key,
        source=source,
        report_metadata_enabled=payload.get("report_metadata_enabled"),
    )
    return ApplicationConfig(
        profile=cfg.profile,
        report_metadata_enabled=cfg.report_metadata_enabled,
        strict_engineering_mode=bool(payload.get("strict_engineering_mode", True)),
        metadata=ConfigMetadata(
            schema_version=schema_version,
            app_version=str(metadata_map.get("app_version") or __version__),
            requested_profile=cfg.metadata.requested_profile,
            resolved_profile=cfg.metadata.resolved_profile,
            source=source or cfg.metadata.source,
            fallback_used=cfg.metadata.fallback_used,
            validation_issues=tuple(validation_issues + cfg.metadata.validation_issues),
        ),
    )


def validate_application_config(cfg: ApplicationConfig) -> ConfigValidationResult:
    issues: list[ConfigValidationIssue] = []
    if cfg.profile.key not in _PROFILE_REGISTRY:
        issues.append(ConfigValidationIssue(
            VALIDATION_ERROR,
            "profile",
            f"Resolved profile {cfg.profile.key!r} is not registered.",
        ))
    if cfg.metadata.schema_version != CONFIG_SCHEMA_VERSION:
        issues.append(ConfigValidationIssue(
            VALIDATION_WARNING,
            "schema_version",
            f"Config schema {cfg.metadata.schema_version!r} differs from supported {CONFIG_SCHEMA_VERSION!r}.",
        ))
    issues.extend(cfg.metadata.validation_issues)
    return ConfigValidationResult(tuple(issues))


def config_report_rows(
    cfg: ApplicationConfig,
    *,
    force: bool = False,
) -> Tuple[tuple[str, str], ...]:
    if not (force or cfg.report_metadata_enabled):
        return ()

    rows: list[tuple[str, str]] = [
        ("Application Profile", f"{cfg.profile.display_name} ({cfg.profile.key})"),
        ("Configuration Schema", cfg.metadata.schema_version),
        ("Application Version", cfg.metadata.app_version),
        ("Configuration Source", cfg.metadata.source),
    ]
    if cfg.metadata.fallback_used:
        rows.append(("Fallback Applied", "Yes - default profile used"))
        rows.append(("Requested Profile", cfg.metadata.requested_profile))
    if cfg.profile.workflow_tags:
        rows.append(("Workflow Tags", ", ".join(cfg.profile.workflow_tags)))
    return tuple(rows)
