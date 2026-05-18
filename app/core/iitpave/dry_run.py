"""IITPAVE dry-run execution readiness checks.

Phase 24 verifies subprocess launch readiness only. It does not build
IITPAVE engineering input, parse output, compute strains, or make IRC:37
compliance claims.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config_profiles import (
    VALIDATION_ERROR,
    VALIDATION_INFO,
    VALIDATION_WARNING,
)

from .discovery import IITPaveEnvironmentIssue
from .runner import ExternalExeRunner
from .runner_config import (
    IITPAVE_RUNNER_EXTERNAL,
    IITPaveRunnerSelectionResult,
)


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IITPaveDryRunConfig:
    """Configuration for an execution-readiness probe.

    The launch probe sends no engineering input. A non-zero return code is
    recorded as a warning because many real console programs fail without
    input while still proving that the OS could launch the process.
    """
    launch_probe: bool = True
    probe_timeout_sec: float = 3.0
    probe_stdin: str = ""
    stdout_preview_chars: int = 300
    stderr_preview_chars: int = 300

    def as_dict(self) -> dict[str, Any]:
        return {
            "launch_probe": self.launch_probe,
            "probe_timeout_sec": self.probe_timeout_sec,
            "probe_stdin": self.probe_stdin,
            "stdout_preview_chars": self.stdout_preview_chars,
            "stderr_preview_chars": self.stderr_preview_chars,
        }


@dataclass(frozen=True, slots=True)
class IITPaveDryRunResult:
    """Audit-friendly result of a dry-run readiness check."""
    selection: IITPaveRunnerSelectionResult
    config: IITPaveDryRunConfig
    command: tuple[str, ...] = ()
    working_dir: str = ""
    launch_attempted: bool = False
    launched: bool = False
    returncode: int | None = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    issues: tuple[IITPaveEnvironmentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and not any(
            i.severity == VALIDATION_ERROR for i in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == VALIDATION_WARNING for i in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": list(self.command),
            "working_dir": self.working_dir,
            "launch_attempted": self.launch_attempted,
            "launched": self.launched,
            "returncode": self.returncode,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "config": self.config.as_dict(),
            "selection": self.selection.as_dict(),
            "issues": [i.as_dict() for i in self.issues],
        }


def _issue(severity: str, field: str, message: str) -> IITPaveEnvironmentIssue:
    return IITPaveEnvironmentIssue(severity=severity, field=field, message=message)


def _preview(text: str | bytes, limit: int) -> str:
    if limit <= 0:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return (text or "")[:limit]


def _blocked(
    selection: IITPaveRunnerSelectionResult,
    config: IITPaveDryRunConfig,
    *,
    reason: str,
    issues: list[IITPaveEnvironmentIssue],
    command: tuple[str, ...] = (),
    working_dir: str = "",
) -> IITPaveDryRunResult:
    log.warning("IITPAVE dry-run readiness blocked: %s", reason)
    return IITPaveDryRunResult(
        selection=selection,
        config=config,
        command=command,
        working_dir=working_dir,
        blocked=True,
        blocked_reason=reason,
        issues=tuple(issues),
    )


def check_iitpave_dry_run_readiness(
    selection: IITPaveRunnerSelectionResult,
    config: IITPaveDryRunConfig | None = None,
) -> IITPaveDryRunResult:
    """Check external IITPAVE launch readiness without engineering output use."""
    cfg = config or IITPaveDryRunConfig()
    issues: list[IITPaveEnvironmentIssue] = list(selection.issues)

    if selection.blocked or not selection.ok:
        reason = selection.blocked_reason or "IITPAVE runner selection is not usable."
        issues.append(_issue(VALIDATION_ERROR, "selection", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues)

    if selection.runner_source != IITPAVE_RUNNER_EXTERNAL:
        reason = "IITPAVE dry-run readiness requires external_exe runner selection."
        issues.append(_issue(VALIDATION_ERROR, "selection.runner_source", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues)

    if not isinstance(selection.runner, ExternalExeRunner):
        reason = "IITPAVE dry-run readiness requires an ExternalExeRunner instance."
        issues.append(_issue(VALIDATION_ERROR, "selection.runner", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues)

    exe_path = Path(selection.runner.exe_path)
    command = (str(exe_path),)
    if not exe_path.is_file():
        reason = f"IITPAVE executable is not available for dry run: {exe_path}"
        issues.append(_issue(VALIDATION_ERROR, "iitpave.executable", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues, command=command)

    if cfg.probe_timeout_sec <= 0:
        reason = "IITPAVE dry-run timeout must be greater than zero."
        issues.append(_issue(VALIDATION_ERROR, "dry_run.timeout", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues, command=command)

    issues.append(_issue(
        VALIDATION_INFO,
        "dry_run.command",
        "Dry-run command uses a single executable path with shell=False.",
    ))

    try:
        if selection.runner.working_dir is not None:
            working_dir = Path(selection.runner.working_dir)
            working_dir.mkdir(parents=True, exist_ok=True)
            if not working_dir.is_dir():
                raise OSError(f"not a directory: {working_dir}")
            temp_ctx = None
        else:
            temp_ctx = tempfile.TemporaryDirectory(prefix="iitpave_dry_run_")
            working_dir = Path(temp_ctx.name)
    except OSError as e:
        reason = f"IITPAVE dry-run working directory is not usable: {e}"
        issues.append(_issue(VALIDATION_ERROR, "dry_run.working_dir", reason))
        return _blocked(selection, cfg, reason=reason, issues=issues, command=command)

    try:
        working_dir_text = str(working_dir)
        issues.append(_issue(
            VALIDATION_INFO,
            "dry_run.working_dir",
            f"Dry-run working directory is usable: {working_dir_text}",
        ))

        if not cfg.launch_probe:
            issues.append(_issue(
                VALIDATION_INFO,
                "dry_run.launch_probe",
                "Subprocess launch probe was skipped by configuration.",
            ))
            return IITPaveDryRunResult(
                selection=selection,
                config=cfg,
                command=command,
                working_dir=working_dir_text,
                launch_attempted=False,
                launched=False,
                issues=tuple(issues),
            )

        try:
            completed = subprocess.run(
                list(command),
                input=cfg.probe_stdin,
                capture_output=True,
                text=True,
                cwd=working_dir_text,
                timeout=cfg.probe_timeout_sec,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as e:
            reason = (
                f"IITPAVE dry-run launch timed out after {cfg.probe_timeout_sec:g}s."
            )
            issues.append(_issue(VALIDATION_ERROR, "dry_run.launch", reason))
            return IITPaveDryRunResult(
                selection=selection,
                config=cfg,
                command=command,
                working_dir=working_dir_text,
                launch_attempted=True,
                launched=True,
                stdout_preview=_preview(e.stdout or "", cfg.stdout_preview_chars),
                stderr_preview=_preview(e.stderr or "", cfg.stderr_preview_chars),
                blocked=True,
                blocked_reason=reason,
                issues=tuple(issues),
            )
        except (OSError, ValueError) as e:
            reason = f"IITPAVE dry-run subprocess launch failed safely: {e}"
            issues.append(_issue(VALIDATION_ERROR, "dry_run.launch", reason))
            return IITPaveDryRunResult(
                selection=selection,
                config=cfg,
                command=command,
                working_dir=working_dir_text,
                launch_attempted=True,
                launched=False,
                blocked=True,
                blocked_reason=reason,
                issues=tuple(issues),
            )

        if completed.returncode != 0:
            issues.append(_issue(
                VALIDATION_WARNING,
                "dry_run.returncode",
                "IITPAVE dry-run process launched but returned non-zero "
                f"code {completed.returncode}; no engineering output was parsed.",
            ))
        else:
            issues.append(_issue(
                VALIDATION_INFO,
                "dry_run.returncode",
                "IITPAVE dry-run process launched and exited with code 0; "
                "no engineering output was parsed.",
            ))

        return IITPaveDryRunResult(
            selection=selection,
            config=cfg,
            command=command,
            working_dir=working_dir_text,
            launch_attempted=True,
            launched=True,
            returncode=completed.returncode,
            stdout_preview=_preview(completed.stdout, cfg.stdout_preview_chars),
            stderr_preview=_preview(completed.stderr, cfg.stderr_preview_chars),
            issues=tuple(issues),
        )
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()
