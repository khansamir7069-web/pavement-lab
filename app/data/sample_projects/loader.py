"""JSON sample-project loader (Phase 16).

Pure-Python; no engine imports here so the loader can be used by
documentation tools and the validation harness without pulling in the
full ``app.core`` dependency tree.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Tuple


_SAMPLE_DIR = Path(__file__).resolve().parent
_FILE_GLOB = "corpus_*.json"


def sample_dir() -> Path:
    """Return the absolute filesystem path of the sample-project directory."""
    return _SAMPLE_DIR


def list_samples() -> Tuple[str, ...]:
    """Return sample names (filename stems, sorted)."""
    return tuple(sorted(p.stem for p in _SAMPLE_DIR.glob(_FILE_GLOB)))


def load_sample(name: str) -> Mapping:
    """Load one sample by stem (e.g. ``"corpus_01_low_traffic_routine"``).

    Raises ``FileNotFoundError`` if the file is missing — the loader
    intentionally does not silently substitute a default.
    """
    path = _SAMPLE_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Sample project not found: {name!r}. "
            f"Available: {list_samples()}"
        )
    return json.loads(path.read_text(encoding="utf-8"))
