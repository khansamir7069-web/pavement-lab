"""Phase-13 output-text parser.

Owns the canonical contract used by ``StubRunner`` today. When the
real IITPAVE exe is bundled (Phase 17), only this file needs refinement
— the rest of the integration layer stays frozen.
"""
from __future__ import annotations

import re

from .pavement_structure import REFERENCES as STRUCTURE_REFERENCES
from .results import MechanisticResult, PLACEHOLDER_NOTE, PointResult
from .runner import SOURCE_EXTERNAL, SOURCE_STUB, STUB_OUTPUT_VERSION


_NUMERIC_PREFIX_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
)

_IITPAVE_HEADER_ALIASES = {
    "z": "z",
    "depth": "z",
    "r": "r",
    "radial": "r",
    "radius": "r",
    "sigmaz": "sigma_z",
    "sigmazz": "sigma_z",
    "sigmat": "sigma_t",
    "sigmatt": "sigma_t",
    "sigmar": "sigma_r",
    "sigmarr": "sigma_r",
    "epz": "epsilon_z",
    "epsz": "epsilon_z",
    "epsilonz": "epsilon_z",
    "ept": "epsilon_t",
    "epst": "epsilon_t",
    "epsilont": "epsilon_t",
    "epr": "epsilon_r",
    "epsr": "epsilon_r",
    "epsilonr": "epsilon_r",
}

_REQUIRED_IITPAVE_COLUMNS = {
    "z",
    "r",
    "sigma_z",
    "sigma_r",
    "sigma_t",
    "epsilon_z",
    "epsilon_r",
    "epsilon_t",
}


def _strip_comments(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _parse_numeric_prefix(token: str) -> float | None:
    match = _NUMERIC_PREFIX_RE.match(token)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _normalize_header_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", token).lower()


def _strain_to_microstrain(value: float) -> float:
    """Normalize IITPAVE strain values to microstrain."""
    if abs(value) < 0.1:
        return value * 1.0e6
    return value


def _parse_counted_rows(
    lines: list[str],
    *,
    source: str,
) -> MechanisticResult:
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


def _header_columns(line: str) -> dict[str, int] | None:
    columns: dict[str, int] = {}
    for idx, token in enumerate(line.split()):
        role = _IITPAVE_HEADER_ALIASES.get(_normalize_header_token(token))
        if role and role not in columns:
            columns[role] = idx
    if _REQUIRED_IITPAVE_COLUMNS.issubset(columns):
        return columns
    return None


def _parse_iitpave_table(lines: list[str]) -> tuple[PointResult, ...]:
    """Parse conservative IITPAVE stress/strain tables.

    Supported tables use the IRC:37 Annex-I output fields: Z, R, SigmaZ,
    SigmaT, SigmaR, epZ, epT and epR. Rows may include the IITPAVE
    interface suffix on depth values, such as ``140L``.
    """
    rows: list[PointResult] = []
    active_columns: dict[str, int] | None = None
    max_idx = 0

    for line in lines:
        header = _header_columns(line)
        if header is not None:
            active_columns = header
            max_idx = max(header.values())
            continue
        if active_columns is None:
            continue

        tokens = line.split()
        if len(tokens) <= max_idx:
            continue
        values: dict[str, float] = {}
        for role, idx in active_columns.items():
            value = _parse_numeric_prefix(tokens[idx])
            if value is None:
                values = {}
                break
            values[role] = value
        if not values:
            continue

        rows.append(PointResult(
            z_mm=values["z"],
            r_mm=values["r"],
            sigma_z_mpa=values["sigma_z"],
            sigma_r_mpa=values["sigma_r"],
            sigma_t_mpa=values["sigma_t"],
            epsilon_z_microstrain=_strain_to_microstrain(values["epsilon_z"]),
            epsilon_r_microstrain=_strain_to_microstrain(values["epsilon_r"]),
            epsilon_t_microstrain=_strain_to_microstrain(values["epsilon_t"]),
        ))

    return tuple(rows)


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
    try:
        return _parse_counted_rows(lines, source=source)
    except (ValueError, IndexError):
        if source != SOURCE_EXTERNAL:
            raise

    table_rows = _parse_iitpave_table(lines)
    if not table_rows:
        raise ValueError(
            "iitpave parser: external IITPAVE output did not contain a "
            "supported stress/strain table with Z, R, SigmaZ, SigmaR, "
            "SigmaT, epZ, epR and epT columns."
        )
    return MechanisticResult(
        point_results=table_rows,
        references=STRUCTURE_REFERENCES,
        is_placeholder=False,
        source=source,
        notes="Parsed from external IITPAVE stress/strain table.",
    )


def is_known_stub_output(text: str) -> bool:
    """Cheap heuristic to detect output we generated ourselves."""
    return STUB_OUTPUT_VERSION in (text or "")
