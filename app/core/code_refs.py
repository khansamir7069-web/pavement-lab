"""Source-tag registry — single point of truth for IRC/MoRTH/IS/ASTM/AASHTO
code citations across specs, binders, engines and reports.

Loaded from ``app/data/code_registry.json`` at import time. A ``CodeRef``
attaches a code id + optional clause/note to any spec, binder or engine
module, so report writers can render uniform citations without hard-coding
strings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Tuple

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "code_registry.json"


@dataclass(frozen=True, slots=True)
class CodeRecord:
    code_id: str          # e.g. "IRC:37-2018"
    title: str
    year: Optional[int]
    org: str              # IRC | MoRTH | BIS | ASTM | AASHTO
    scope: str


@dataclass(frozen=True, slots=True)
class CodeRef:
    """Citation attached to a spec / binder / engine module."""
    code_id: str
    clause: str = ""      # e.g. "cl. 6.5" / "Table 500-9" / "Annex E"
    note: str = ""

    def label(self, registry: Mapping[str, CodeRecord] | None = None) -> str:
        registry = registry if registry is not None else CODE_REGISTRY
        rec = registry.get(self.code_id)
        title = rec.title if rec else ""
        parts = [self.code_id]
        if self.clause:
            parts.append(self.clause)
        if title:
            parts.append(f"— {title}")
        if self.note:
            parts.append(f"({self.note})")
        return " ".join(parts)


def _load() -> dict[str, CodeRecord]:
    if not _REGISTRY_PATH.is_file():
        return {}
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, CodeRecord] = {}
    for cid, rec in (data.get("codes") or {}).items():
        out[cid] = CodeRecord(
            code_id=cid,
            title=rec.get("title", ""),
            year=rec.get("year"),
            org=rec.get("org", ""),
            scope=rec.get("scope", ""),
        )
    return out


CODE_REGISTRY: dict[str, CodeRecord] = _load()


def get_code(code_id: str) -> Optional[CodeRecord]:
    return CODE_REGISTRY.get(code_id)


def parse_refs(raw: Iterable[Mapping] | None) -> Tuple[CodeRef, ...]:
    """Build a tuple of ``CodeRef`` from a list-of-dicts loaded from JSON."""
    if not raw:
        return ()
    out: list[CodeRef] = []
    for item in raw:
        cid = item.get("code_id") or item.get("code") or ""
        if not cid:
            continue
        out.append(CodeRef(
            code_id=cid,
            clause=item.get("clause", "") or "",
            note=item.get("note", "") or "",
        ))
    return tuple(out)


def labels(refs: Iterable[CodeRef]) -> list[str]:
    return [r.label() for r in refs]
