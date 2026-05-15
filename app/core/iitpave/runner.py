"""Phase-13 execution-abstraction layer.

Two implementations of the same Protocol:

* ``StubRunner``       — in-process placeholder; produces deterministic
                         output text consumable by ``parse_iitpave_output``.
                         Heuristic is transparent and clearly flagged
                         placeholder (NOT a real elastic-layer solution).
* ``ExternalExeRunner``— declared so callers can program against the
                         real-exe code path today. Calling ``run()`` raises
                         ``NotImplementedError``; bundling lands with
                         Phase 17.

The interface is intentionally narrow — runners see only opaque input /
output text. No domain knowledge crosses the runner boundary, which keeps
unit tests trivial and the real-exe swap a single-file change.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol


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
# External-exe runner (declared; not implemented in V1)
# ---------------------------------------------------------------------------

class ExternalExeRunner:
    """Real-exe runner. Constructor wired; ``run`` is intentionally a
    hard failure in V1 so callers cannot silently fall back to fake data.
    Bundling lands with Phase 17.
    """
    source: str = SOURCE_EXTERNAL

    def __init__(self, exe_path: Path | str | None = None) -> None:
        self.exe_path: Path | None = Path(exe_path) if exe_path else None

    def run(self, input_text: str) -> str:
        raise NotImplementedError(
            "IITPAVE executable is not bundled in V1 — use StubRunner. "
            "External-exe support lands with Phase 17 (EXE / installer build)."
        )
