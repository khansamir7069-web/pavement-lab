"""Safe IITPAVE runner selection/configuration layer.

Phase 23 keeps runner choice explicit. The default remains the deterministic
stub. A caller must request ``external_exe`` before this module will select
the real subprocess runner, and that request is blocked unless Phase-22
environment validation finds a usable executable path.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)

from .discovery import (
    IITPaveEnvironmentIssue,
    IITPaveEnvironmentValidationResult,
    discover_iitpave_executable,
    validate_iitpave_environment,
)
from .runner import ExternalExeRunner, IITPaveRunner, StubRunner


log = logging.getLogger(__name__)

IITPAVE_RUNNER_STUB = "stub"
IITPAVE_RUNNER_EXTERNAL = "external_exe"
SUPPORTED_IITPAVE_RUNNER_MODES = (
    IITPAVE_RUNNER_STUB,
    IITPAVE_RUNNER_EXTERNAL,
)


@dataclass(frozen=True, slots=True)
class IITPaveRunnerConfig:
    """Configuration used to choose a safe IITPAVE runner.

    ``mode="stub"`` preserves the current V1 behavior. ``mode="external_exe"``
    requests real IITPAVE execution but does not guarantee it; selection is
    blocked unless executable discovery and execution-risk checks pass.
    """
    mode: str = IITPAVE_RUNNER_STUB
    configured_executable_path: str = ""
    include_path_search: bool = False
    timeout_sec: float = 60.0
    working_dir: str = ""
    use_stdin_stdout: bool = True
    input_filename: str = "iitp_inp.dat"
    output_filename: str = "iitp_out.dat"
    bc_min: float = 30.0
    bc_max: float = 80.0
    dbm_min: float = 50.0
    dbm_max: float = 300.0
    wmm_min: float = 75.0
    wmm_max: float = 250.0
    gsb_min: float = 100.0
    gsb_max: float = 400.0
    max_iterations: int = 15

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "configured_executable_path": self.configured_executable_path,
            "include_path_search": self.include_path_search,
            "timeout_sec": self.timeout_sec,
            "working_dir": self.working_dir,
            "use_stdin_stdout": self.use_stdin_stdout,
            "input_filename": self.input_filename,
            "output_filename": self.output_filename,
            "bc_min": self.bc_min,
            "bc_max": self.bc_max,
            "dbm_min": self.dbm_min,
            "dbm_max": self.dbm_max,
            "wmm_min": self.wmm_min,
            "wmm_max": self.wmm_max,
            "gsb_min": self.gsb_min,
            "gsb_max": self.gsb_max,
            "max_iterations": self.max_iterations,
        }


@dataclass(frozen=True, slots=True)
class IITPaveRunnerSelectionResult:
    """Audit-friendly outcome of a runner selection attempt."""
    config: IITPaveRunnerConfig
    runner_source: str
    runner: IITPaveRunner | None = field(default=None, repr=False, compare=False)
    selected_path: Path | None = None
    selected_candidate_source: str = ""
    environment: IITPaveEnvironmentValidationResult | None = None
    blocked: bool = False
    blocked_reason: str = ""
    fallback_used: bool = False
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and self.runner is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "runner_source": self.runner_source,
            "selected_path": str(self.selected_path) if self.selected_path else "",
            "selected_candidate_source": self.selected_candidate_source,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "fallback_used": self.fallback_used,
            "config": self.config.as_dict(),
            "environment": (
                self.environment.as_dict() if self.environment is not None else None
            ),
            "issues": [i.as_dict() for i in self.issues],
        }


def iitpave_runner_config_from_mapping(
    payload: Mapping[str, Any] | None,
) -> IITPaveRunnerConfig:
    """Load runner config from a mapping without requiring a DB/schema change."""
    if not isinstance(payload, Mapping):
        return IITPaveRunnerConfig()
    return IITPaveRunnerConfig(
        mode=str(payload.get("mode") or IITPAVE_RUNNER_STUB).strip() or IITPAVE_RUNNER_STUB,
        configured_executable_path=str(
            payload.get("configured_executable_path")
            or payload.get("executable_path")
            or ""
        ).strip(),
        include_path_search=bool(payload.get("include_path_search", False)),
        timeout_sec=float(payload.get("timeout_sec", 60.0) or 60.0),
        working_dir=str(payload.get("working_dir") or "").strip(),
        use_stdin_stdout=bool(payload.get("use_stdin_stdout", True)),
        input_filename=str(payload.get("input_filename") or "iitp_inp.dat").strip(),
        output_filename=str(payload.get("output_filename") or "iitp_out.dat").strip(),
        bc_min=float(payload.get("bc_min", 30.0)),
        bc_max=float(payload.get("bc_max", 80.0)),
        dbm_min=float(payload.get("dbm_min", 50.0)),
        dbm_max=float(payload.get("dbm_max", 300.0)),
        wmm_min=float(payload.get("wmm_min", 75.0)),
        wmm_max=float(payload.get("wmm_max", 250.0)),
        gsb_min=float(payload.get("gsb_min", 100.0)),
        gsb_max=float(payload.get("gsb_max", 400.0)),
        max_iterations=int(payload.get("max_iterations", 15)),
    )


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _candidate_source(
    environment: IITPaveEnvironmentValidationResult,
    selected_path: Path | None,
) -> str:
    if selected_path is None:
        return ""
    for candidate in environment.candidates:
        if candidate.path == selected_path:
            return candidate.source
    return ""


def _execution_risk_issues(path: Path) -> tuple[IITPaveEnvironmentIssue, ...]:
    """Classify filesystem execution risks without launching the binary."""
    issues: list[IITPaveEnvironmentIssue] = []
    try:
        stat = path.stat()
    except (OSError, ValueError) as e:
        return (_issue(
            VALIDATION_ERROR,
            "iitpave.executable",
            f"IITPAVE executable could not be inspected: {path} ({e})",
        ),)

    if stat.st_size <= 0:
        issues.append(_issue(
            VALIDATION_ERROR,
            "iitpave.executable",
            f"IITPAVE executable is empty and will not be used: {path}",
        ))
    if not os.access(path, os.R_OK):
        issues.append(_issue(
            VALIDATION_ERROR,
            "iitpave.executable",
            f"IITPAVE executable is not readable by this process: {path}",
        ))
    if os.name != "nt" and not os.access(path, os.X_OK):
        issues.append(_issue(
            VALIDATION_ERROR,
            "iitpave.executable",
            f"IITPAVE executable lacks execute permission: {path}",
        ))
    if os.name == "nt" and path.suffix.lower() not in (".exe", ".bat", ".cmd", ".com"):
        issues.append(_issue(
            VALIDATION_WARNING,
            "iitpave.executable",
            "Selected IITPAVE path has an unusual Windows executable suffix; "
            f"version/output validation is still required before compliance use: {path}",
        ))
    return tuple(issues)


def select_iitpave_runner(
    config: IITPaveRunnerConfig | Mapping[str, Any] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    app_dir: Path | str | None = None,
) -> IITPaveRunnerSelectionResult:
    """Select a runner or return an explicit blocked-execution result."""
    cfg = (
        config
        if isinstance(config, IITPaveRunnerConfig)
        else iitpave_runner_config_from_mapping(config)
    )
    issues: list[IITPaveEnvironmentIssue] = []

    if cfg.mode not in SUPPORTED_IITPAVE_RUNNER_MODES:
        issues.append(_issue(
            VALIDATION_ERROR,
            "mode",
            f"Unsupported IITPAVE runner mode {cfg.mode!r}.",
        ))
        return IITPaveRunnerSelectionResult(
            config=cfg,
            runner_source="",
            blocked=True,
            blocked_reason="Unsupported IITPAVE runner mode.",
            issues=tuple(issues),
        )

    if cfg.mode == IITPAVE_RUNNER_STUB:
        candidates = discover_iitpave_executable(
            configured_path=cfg.configured_executable_path or None,
            env=env,
            include_path_search=cfg.include_path_search,
            app_dir=app_dir,
        )
        environment = IITPaveEnvironmentValidationResult(
            candidates=candidates,
            selected_path=None,
            issues=(),
        )
        issues.append(_issue(
            VALIDATION_INFO,
            "mode",
            "IITPAVE stub runner selected; no real IITPAVE executable will be used.",
        ))
        return IITPaveRunnerSelectionResult(
            config=cfg,
            runner_source=IITPAVE_RUNNER_STUB,
            runner=StubRunner(),
            environment=environment,
            fallback_used=False,
            issues=tuple(issues),
        )

    environment = validate_iitpave_environment(
        configured_path=cfg.configured_executable_path or None,
        env=env,
        include_path_search=cfg.include_path_search,
        app_dir=app_dir,
    )
    issues.extend(environment.issues)
    selected_path = environment.selected_path
    if selected_path is not None:
        issues.extend(_execution_risk_issues(selected_path))

    error_issues = [i for i in issues if i.severity == VALIDATION_ERROR]
    if not environment.ok or error_issues or selected_path is None:
        reason = (
            error_issues[0].message
            if error_issues
            else "IITPAVE executable configuration is invalid."
        )
        log.warning("IITPAVE external runner blocked: %s", reason)
        return IITPaveRunnerSelectionResult(
            config=cfg,
            runner_source=IITPAVE_RUNNER_EXTERNAL,
            selected_path=selected_path,
            selected_candidate_source=_candidate_source(environment, selected_path),
            environment=environment,
            blocked=True,
            blocked_reason=reason,
            issues=tuple(issues),
        )

    working_dir = Path(cfg.working_dir) if cfg.working_dir else None
    runner = ExternalExeRunner(
        exe_path=selected_path,
        timeout_sec=cfg.timeout_sec,
        working_dir=working_dir,
        use_stdin_stdout=cfg.use_stdin_stdout,
        input_filename=cfg.input_filename or "iitp_inp.dat",
        output_filename=cfg.output_filename or "iitp_out.dat",
    )
    log.debug("IITPAVE external runner selected: %s", selected_path)
    return IITPaveRunnerSelectionResult(
        config=cfg,
        runner_source=IITPAVE_RUNNER_EXTERNAL,
        runner=runner,
        selected_path=selected_path,
        selected_candidate_source=_candidate_source(environment, selected_path),
        environment=environment,
        blocked=False,
        issues=tuple(issues),
    )
