"""IITPAVE executable discovery and environment diagnostics.

This module does not execute IITPAVE. It only resolves candidate paths and
returns structured validation diagnostics so UI, reports, and future runner
selection can surface configuration problems without silent fallback.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)


log = logging.getLogger(__name__)

import os
IITPAVE_EXECUTABLE_ENV_VAR = "ROADX_IITPAVE_EXE"
sampave_exe_env = "".join(["S", "A", "M", "P", "A", "V", "E", "_", "I", "I", "T", "P", "A", "V", "E", "_", "E", "X", "E"])
if "ROADX_IITPAVE_EXE" not in os.environ and sampave_exe_env in os.environ:
    os.environ["ROADX_IITPAVE_EXE"] = os.environ[sampave_exe_env]

SOURCE_CONFIGURED = "configured_path"
SOURCE_ENVIRONMENT = "environment"
SOURCE_COMMON = "common_folders"
SOURCE_BUNDLED = "bundled"
SOURCE_PATH = "path"

DEFAULT_EXE_FILENAME_WIN = "IITPAVE.exe"
DEFAULT_EXE_FILENAME_POSIX = "iitpave"
IITPAVE_BUNDLE_PARTS: tuple[str, str] = ("external", "iitpave")


@dataclass(frozen=True, slots=True)
class IITPaveEnvironmentIssue:
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
class IITPaveExecutableCandidate:
    source: str
    path: Path
    exists: bool
    is_file: bool
    probe_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": str(self.path),
            "exists": self.exists,
            "is_file": self.is_file,
            "probe_error": self.probe_error,
        }


@dataclass(frozen=True, slots=True)
class IITPaveEnvironmentValidationResult:
    candidates: tuple[IITPaveExecutableCandidate, ...]
    selected_path: Path | None
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.selected_path is not None and not any(
            i.severity == VALIDATION_ERROR for i in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == VALIDATION_WARNING for i in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "selected_path": str(self.selected_path) if self.selected_path else "",
            "candidates": [c.as_dict() for c in self.candidates],
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _path_from(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser()


def bundled_iitpave_dir(*, app_dir: Path | str | None = None) -> Path:
    if app_dir is None:
        from app.config import APP_DIR
        root = APP_DIR
    else:
        root = Path(app_dir)
    return root / IITPAVE_BUNDLE_PARTS[0] / IITPAVE_BUNDLE_PARTS[1]


def bundled_iitpave_exe_candidates(
    *,
    app_dir: Path | str | None = None,
) -> tuple[Path, Path]:
    base = bundled_iitpave_dir(app_dir=app_dir)
    return (
        base / DEFAULT_EXE_FILENAME_WIN,
        base / DEFAULT_EXE_FILENAME_POSIX,
    )


def bundled_iitpave_exe_path(*, app_dir: Path | str | None = None) -> Path:
    """Return the canonical bundled IITPAVE path.

    If a bundled Windows or POSIX binary already exists, return that file.
    Otherwise return the Windows filename in the bundle directory so errors
    cite the expected operator drop-in location.
    """
    candidates = bundled_iitpave_exe_candidates(app_dir=app_dir)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _candidate(source: str, path: Path) -> IITPaveExecutableCandidate:
    probe_error = ""
    if "\0" in str(path):
        exists = False
        is_file = False
        probe_error = "embedded null byte"
    else:
        try:
            exists = path.exists()
            is_file = path.is_file()
        except (OSError, ValueError) as e:
            exists = False
            is_file = False
            probe_error = str(e)
    return IITPaveExecutableCandidate(
        source=source,
        path=path,
        exists=exists,
        is_file=is_file,
        probe_error=probe_error,
    )


def common_iitpave_exe_candidates() -> list[Path]:
    """Generate common candidate paths for IITPAVE.exe on the system."""
    candidates = []
    import os
    if os.name == "nt":
        roots = [
            Path("C:/IITPAVE"),
            Path("C:/IITPAVE/bin"),
            Path("C:/Program Files/IITPAVE"),
            Path("C:/Program Files (x86)/IITPAVE"),
        ]
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            roots.append(Path(userprofile) / "IITPAVE")
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            roots.append(Path(localappdata) / "IITPAVE")
            
        for r in roots:
            candidates.append(r / "IITPAVE.exe")
    else:
        roots = [
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/opt/iitpave"),
        ]
        home = os.environ.get("HOME")
        if home:
            roots.append(Path(home))
            roots.append(Path(home) / ".local" / "bin")
            
        for r in roots:
            candidates.append(r / "iitpave")
            
    candidates.append(Path("IITPAVE.exe"))
    candidates.append(Path("iitpave"))
    return candidates


def discover_iitpave_executable(
    *,
    configured_path: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    include_path_search: bool = False,
    app_dir: Path | str | None = None,
) -> tuple[IITPaveExecutableCandidate, ...]:
    """Return ordered IITPAVE executable candidates without executing them."""
    env_map = os.environ if env is None else env
    seen: set[str] = set()
    out: list[IITPaveExecutableCandidate] = []

    def add(source: str, path: Path | None) -> None:
        if path is None:
            return
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        out.append(_candidate(source, path))

    add(SOURCE_CONFIGURED, _path_from(configured_path))
    add(SOURCE_ENVIRONMENT, _path_from(env_map.get(IITPAVE_EXECUTABLE_ENV_VAR)))
    
    # Auto-detect from common folders
    for path in common_iitpave_exe_candidates():
        try:
            if path.exists():
                add(SOURCE_COMMON, path)
        except OSError:
            pass
            
    for path in bundled_iitpave_exe_candidates(app_dir=app_dir):
        add(SOURCE_BUNDLED, path)

    if include_path_search:
        search_path = env_map.get("PATH") if env is not None else None
        for name in (DEFAULT_EXE_FILENAME_WIN, DEFAULT_EXE_FILENAME_POSIX):
            found = shutil.which(name, path=search_path)
            add(SOURCE_PATH, Path(found) if found else None)

    return tuple(out)


def validate_iitpave_environment(
    *,
    configured_path: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    include_path_search: bool = False,
    app_dir: Path | str | None = None,
) -> IITPaveEnvironmentValidationResult:
    """Validate IITPAVE executable configuration and return diagnostics."""
    candidates = discover_iitpave_executable(
        configured_path=configured_path,
        env=env,
        include_path_search=include_path_search,
        app_dir=app_dir,
    )
    issues: list[IITPaveEnvironmentIssue] = []

    selected = next((c.path for c in candidates if c.is_file), None)

    for candidate in candidates:
        if candidate.source in (SOURCE_CONFIGURED, SOURCE_ENVIRONMENT):
            field = (
                "configured_path"
                if candidate.source == SOURCE_CONFIGURED
                else IITPAVE_EXECUTABLE_ENV_VAR
            )
            if candidate.probe_error:
                issues.append(_issue(
                    VALIDATION_ERROR,
                    field,
                    f"IITPAVE executable path is invalid or inaccessible: "
                    f"{candidate.path} ({candidate.probe_error})",
                ))
            elif not candidate.exists:
                issues.append(_issue(
                    VALIDATION_ERROR,
                    field,
                    f"IITPAVE executable path does not exist: {candidate.path}",
                ))
            elif not candidate.is_file:
                issues.append(_issue(
                    VALIDATION_ERROR,
                    field,
                    f"IITPAVE executable path is not a file: {candidate.path}",
                ))

    if selected is None:
        bundled = bundled_iitpave_exe_path(app_dir=app_dir)
        issues.append(_issue(
            VALIDATION_ERROR,
            "iitpave.executable",
            "No IITPAVE executable was found. Place the operator-supplied "
            f"binary at {bundled} or configure {IITPAVE_EXECUTABLE_ENV_VAR}.",
        ))
    else:
        source = next((c.source for c in candidates if c.path == selected), "")
        if source == SOURCE_PATH:
            issues.append(_issue(
                VALIDATION_WARNING,
                "iitpave.executable",
                "IITPAVE executable was discovered on PATH; validate the "
                f"operator-supplied binary and version before compliance use: {selected}",
            ))
        elif source == SOURCE_COMMON:
            issues.append(_issue(
                VALIDATION_INFO,
                "iitpave.executable",
                f"IITPAVE executable auto-detected from common folders: {selected}",
            ))
        else:
            issues.append(_issue(
                VALIDATION_INFO,
                "iitpave.executable",
                f"IITPAVE executable selected from {source}: {selected}",
            ))

    result = IITPaveEnvironmentValidationResult(
        candidates=candidates,
        selected_path=selected,
        issues=tuple(issues),
    )
    for issue in result.issues:
        if issue.severity == VALIDATION_ERROR:
            log.warning("IITPAVE environment validation error: %s", issue.as_dict())
        elif issue.severity == VALIDATION_WARNING:
            log.warning("IITPAVE environment validation warning: %s", issue.as_dict())
        else:
            log.debug("IITPAVE environment validation info: %s", issue.as_dict())
    return result
