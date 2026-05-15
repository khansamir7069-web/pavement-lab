"""Phase-13 output-text parser.

Owns the canonical contract used by ``StubRunner`` today. When the
real IITPAVE exe is bundled (Phase 17), only this file needs refinement
— the rest of the integration layer stays frozen.
"""
from __future__ import annotations

from typing import Tuple

from .pavement_structure import REFERENCES as STRUCTURE_REFERENCES
from .results import MechanisticResult, PLACEHOLDER_NOTE, PointResult
from .runner import SOURCE_STUB, STUB_OUTPUT_VERSION


def _strip_comments(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def parse_iitpave_output(
    text: str,
    *,
    source: str = SOURCE_STUB,
) -> MechanisticResult:
    """Parse an IITPAVE-style output text block.

    The first non-comment line is the point count. Each subsequent line is:

        z r σ_z σ_r σ_t ε_z ε_r ε_t [label]

    (whitespace-separated, label optional). σ in MPa, ε in micro-strain.
    """
    lines = _strip_comments(text)
    if not lines:
        return MechanisticResult(
            point_results=(),
            references=STRUCTURE_REFERENCES,
            is_placeholder=True,
            source=source,
            notes=PLACEHOLDER_NOTE,
        )
    n = int(lines[0])
    rows: list[PointResult] = []
    for raw in lines[1:1 + n]:
        tokens = raw.split()
        if len(tokens) < 8:
            raise ValueError(
                f"iitpave parser: expected >=8 tokens per row, got {len(tokens)}: {raw!r}"
            )
        rows.append(PointResult(
            z_mm=float(tokens[0]),
            r_mm=float(tokens[1]),
            sigma_z_mpa=float(tokens[2]),
            sigma_r_mpa=float(tokens[3]),
            sigma_t_mpa=float(tokens[4]),
            epsilon_z_microstrain=float(tokens[5]),
            epsilon_r_microstrain=float(tokens[6]),
            epsilon_t_microstrain=float(tokens[7]),
        ))
    return MechanisticResult(
        point_results=tuple(rows),
        references=STRUCTURE_REFERENCES,
        is_placeholder=(source == SOURCE_STUB),
        source=source,
        notes=PLACEHOLDER_NOTE if source == SOURCE_STUB else "",
    )


def is_known_stub_output(text: str) -> bool:
    """Cheap heuristic to detect output we generated ourselves."""
    return STUB_OUTPUT_VERSION in (text or "")
