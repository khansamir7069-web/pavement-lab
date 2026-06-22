"""Phase-13/17 execution-abstraction layer.

Two implementations of the same Protocol:

* ``StubRunner``       — in-process placeholder; produces deterministic
                         output text consumable by ``parse_iitpave_output``.
                         Heuristic is transparent and clearly flagged
                         placeholder (NOT a real elastic-layer solution).
* ``ExternalExeRunner``— Phase 17 subprocess seam. Supports stdin/stdout
                         exchange (modern Fortran builds) and file-based
                         exchange (legacy IRC:37 IITPAVE 6.0 convention,
                         ``iitp_inp.dat`` / ``iitp_out.dat``). Raises a
                         typed ``FileNotFoundError`` when the exe is not
                         bundled — never silently falls back to fake
                         data (placeholder-safety contract).

The interface is intentionally narrow — runners see only opaque input /
output text. No domain knowledge crosses the runner boundary, which keeps
unit tests trivial and the parser the only contract owner.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

from app.config import USER_DATA_DIR
from .discovery import bundled_iitpave_exe_path


SOURCE_STUB: str = "stub"
SOURCE_EXTERNAL: str = "external_exe"

# Stub output format owned by this module + the parser. Both must move
# together when a real exe is bundled.
STUB_OUTPUT_VERSION: str = "PHASE13_STUB_V1"


class IITPaveRunner(Protocol):
    """Anything that turns IITPAVE input text into IITPAVE output text."""

    source: str

    def run(self, input_text: str) -> str: ...


# ---------------------------------------------------------------------------
# Stub runner
# ---------------------------------------------------------------------------

def _parse_stub_input(text: str):
    """Parse our own input format (see input_builder.py)."""
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    it = iter(lines)
    n_layers = int(next(it))
    layers = []
    for _ in range(n_layers):
        tokens = next(it).split()
        e_mpa = float(tokens[0])
        mu    = float(tokens[1])
        h_mm  = float(tokens[2])  # 0 = semi-infinite subgrade
        layers.append((e_mpa, mu, h_mm))
    load_tokens = next(it).split()
    load_p_kn   = float(load_tokens[0])
    pressure    = float(load_tokens[1])  # MPa
    spacing     = float(load_tokens[2])
    n_points = int(next(it))
    points = []
    for _ in range(n_points):
        tokens = next(it).split()
        z = float(tokens[0]); r = float(tokens[1])
        label = tokens[2] if len(tokens) > 2 else "-"
        points.append((z, r, label))
    return layers, (load_p_kn, pressure, spacing), points


def _layer_at_depth(layers, z_mm: float):
    """Return (E, mu) of the layer containing depth ``z_mm`` (top-down).

    The last entry (h=0) is treated as semi-infinite and used for any
    depth at or below the cumulative finite thickness.
    """
    depth_acc = 0.0
    for e_mpa, mu, h_mm in layers[:-1]:
        depth_acc += h_mm
        if z_mm < depth_acc:
            return e_mpa, mu
    # Falls into the subgrade
    e_mpa, mu, _ = layers[-1]
    return e_mpa, mu


def _stub_point_response(z_mm: float, p_mpa: float,
                         e_mpa: float, mu: float):
    """Transparent placeholder σ/ε heuristic.

    NOT a real Boussinesq / Burmister solution. Produces non-zero,
    monotonically-decaying values so downstream consumers can be
    exercised. ``MechanisticResult.is_placeholder=True`` propagates to
    the caller so this is never mistaken for a calibrated result.

    σ_z = p × exp(−z / 250 mm)                  (PLACEHOLDER decay)
    σ_r = σ_t = σ_z × 0.25                      (PLACEHOLDER lateral ratio)
    ε_i  computed by 1-D Hooke (NOT elastic-layer theory).
    """
    sigma_z = p_mpa * math.exp(-z_mm / 250.0)
    sigma_r = sigma_z * 0.25
    sigma_t = sigma_r
    e_safe = max(e_mpa, 1.0)
    eps_z = (sigma_z - 2.0 * mu * sigma_r) / e_safe
    eps_r = ((1.0 - mu) * sigma_r - mu * sigma_z) / e_safe
    eps_t = eps_r
    # Engineering convention: micro-strain.
    return (sigma_z, sigma_r, sigma_t,
            eps_z * 1.0e6, eps_r * 1.0e6, eps_t * 1.0e6)


class StubRunner:
    """In-process deterministic placeholder runner.

    Pure function of the input text — same input always yields the same
    output. Safe to use from tests, reports, and offline workflows.
    """
    source: str = SOURCE_STUB

    def run(self, input_text: str) -> str:
        layers, load, points = _parse_stub_input(input_text)
        _, p_mpa, _ = load
        out: list[str] = []
        out.append(f"# pavement_lab iitpave stub output ({STUB_OUTPUT_VERSION})")
        out.append("# PLACEHOLDER values — see PLACEHOLDER_NOTE in results.py")
        out.append(str(len(points)))
        for z, r, label in points:
            e_mpa, mu = _layer_at_depth(layers, z)
            sz, sr, st, ez, er, et = _stub_point_response(z, p_mpa, e_mpa, mu)
            out.append(
                f"{z:.4f} {r:.4f} "
                f"{sz:.6f} {sr:.6f} {st:.6f} "
                f"{ez:.6f} {er:.6f} {et:.6f} "
                f"{label or '-'}"
            )
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# External-exe runner — Phase 17 subprocess seam
# ---------------------------------------------------------------------------

# Canonical bundle location for the IITPAVE executable. Phase 17 ships
# the directory layout but NOT the binary (binary is licensed / placed
# by the operator per build/installer/bundle_iitpave.md). Phase 22 moves
# path resolution into discovery.py so diagnostics and runner defaults
# share the same filesystem contract.
def default_iitpave_exe_path() -> Path:
    """Return the canonical bundled path for the IITPAVE executable.

    ``APP_DIR / "external" / "iitpave" / IITPAVE.exe`` under the
    PyInstaller bundle (or the source tree, when developing). The
    returned path is honest about the canonical location even when no
    binary is present — caller checks ``.is_file()`` before invoking.
    """
    return bundled_iitpave_exe_path()


class ExternalExeRunner:
    """Subprocess runner for the bundled IITPAVE executable.

    Two exchange modes (selectable via ``use_stdin_stdout``):

      * stdin/stdout (default; modern Fortran builds support this) —
        ``input_text`` is piped to the process and ``stdout`` is
        returned verbatim.
      * file-based (legacy IRC:37 IITPAVE 6.0 convention) — input is
        written to ``<working_dir>/<input_filename>``, the exe is
        invoked with ``working_dir`` as cwd, and the output is read
        back from ``<working_dir>/<output_filename>``.

    The parser (``app.core.iitpave.parser.parse_iitpave_output``)
    remains the single contract owner — this runner is opaque
    text-in / text-out.

    Placeholder-safety contract: when the configured ``exe_path`` does
    not exist on disk, ``run()`` raises ``FileNotFoundError`` with a
    pointer to ``build/installer/bundle_iitpave.md``. The runner never
    silently falls back to a stub.
    """
    source: str = SOURCE_EXTERNAL

    def __init__(
        self,
        exe_path: Path | str | None = None,
        *,
        timeout_sec: float = 60.0,
        working_dir: Path | str | None = None,
        use_stdin_stdout: bool = True,
        input_filename: str = "iitp_inp.dat",
        output_filename: str = "iitp_out.dat",
    ) -> None:
        if exe_path is None:
            self.exe_path: Path = default_iitpave_exe_path()
        else:
            self.exe_path = Path(exe_path)
        self.timeout_sec = float(timeout_sec)
        self.working_dir: Optional[Path] = (
            Path(working_dir) if working_dir is not None else None
        )
        self.use_stdin_stdout = bool(use_stdin_stdout)
        self.input_filename = input_filename
        self.output_filename = output_filename

    # ---- public --------------------------------------------------------
    def run(self, input_text: str) -> str:
        if not self.exe_path.is_file():
            raise FileNotFoundError(
                f"IITPAVE executable not found at {self.exe_path}. "
                "Place the binary per build/installer/bundle_iitpave.md "
                "or fall back to StubRunner for placeholder runs."
            )
        if self.use_stdin_stdout:
            return self._run_stdin_stdout(input_text)
        return self._run_file_based(input_text)

    # ---- internals -----------------------------------------------------
    def _run_stdin_stdout(self, input_text: str) -> str:
        runs_dir = USER_DATA_DIR / "iitpave_runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        inp_path = run_dir / self.input_filename
        inp_path.write_text(input_text, encoding="utf-8")

        start_time = time.time()
        completed = None
        error_msg = ""
        status = "failed"
        returncode = None
        stdout_content = ""
        stderr_content = ""
        output_content = ""

        try:
            completed = subprocess.run(
                [str(self.exe_path)],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=str(run_dir),
                timeout=self.timeout_sec,
                check=False,
            )
            duration = time.time() - start_time
            returncode = completed.returncode
            stdout_content = completed.stdout or ""
            stderr_content = completed.stderr or ""
            if completed.returncode == 0:
                output_content = stdout_content
                status = "success"
            else:
                error_msg = f"IITPAVE exit code {completed.returncode}; stderr: {stderr_content.strip()[:500]}"
                status = f"exit_code_{completed.returncode}"
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            status = "timeout"
            error_msg = f"IITPAVE subprocess timed out after {self.timeout_sec:g}s"
            stdout_content = e.stdout or ""
            stderr_content = e.stderr or ""
        except Exception as e:
            duration = time.time() - start_time
            status = "error"
            error_msg = str(e)

        # Save artifacts
        (run_dir / "stdout.log").write_text(stdout_content, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr_content, encoding="utf-8")
        (run_dir / self.output_filename).write_text(output_content, encoding="utf-8")

        run_status = {
            "timestamp": datetime.now().isoformat(),
            "executable": str(self.exe_path),
            "status": status,
            "duration_sec": duration,
            "error": error_msg,
            "returncode": returncode
        }
        (run_dir / "run_status.json").write_text(json.dumps(run_status, indent=4), encoding="utf-8")

        if status == "timeout":
            raise TimeoutError(error_msg)
        elif status in ("error", "failed") or (returncode is not None and returncode != 0):
            raise RuntimeError(error_msg or f"IITPAVE run failed with status: {status}")

        return output_content

    def _run_file_based(self, input_text: str) -> str:
        runs_dir = USER_DATA_DIR / "iitpave_runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        inp_path = run_dir / self.input_filename
        inp_path.write_text(input_text, encoding="utf-8")

        start_time = time.time()
        completed = None
        error_msg = ""
        status = "failed"
        returncode = None
        stdout_content = ""
        stderr_content = ""
        output_content = ""

        try:
            completed = subprocess.run(
                [str(self.exe_path)],
                capture_output=True,
                text=True,
                cwd=str(run_dir),
                timeout=self.timeout_sec,
                check=False,
            )
            duration = time.time() - start_time
            returncode = completed.returncode
            stdout_content = completed.stdout or ""
            stderr_content = completed.stderr or ""
            if completed.returncode == 0:
                out_path = run_dir / self.output_filename
                if out_path.is_file():
                    output_content = out_path.read_text(encoding="utf-8")
                    status = "success"
                else:
                    error_msg = f"IITPAVE completed with code 0 but produced no output file at {self.output_filename}"
                    status = "output_missing"
            else:
                error_msg = f"IITPAVE exit code {completed.returncode}; stderr: {stderr_content.strip()[:500]}"
                status = f"exit_code_{completed.returncode}"
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            status = "timeout"
            error_msg = f"IITPAVE subprocess timed out after {self.timeout_sec:g}s"
            stdout_content = e.stdout or ""
            stderr_content = e.stderr or ""
        except Exception as e:
            duration = time.time() - start_time
            status = "error"
            error_msg = str(e)

        # Save artifacts
        (run_dir / "stdout.log").write_text(stdout_content, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr_content, encoding="utf-8")
        (run_dir / self.output_filename).write_text(output_content, encoding="utf-8")

        run_status = {
            "timestamp": datetime.now().isoformat(),
            "executable": str(self.exe_path),
            "status": status,
            "duration_sec": duration,
            "error": error_msg,
            "returncode": returncode
        }
        (run_dir / "run_status.json").write_text(json.dumps(run_status, indent=4), encoding="utf-8")

        if status == "timeout":
            raise TimeoutError(error_msg)
        elif status in ("error", "failed", "output_missing") or (returncode is not None and returncode != 0):
            raise RuntimeError(error_msg or f"IITPAVE run failed with status: {status}")

        return output_content
