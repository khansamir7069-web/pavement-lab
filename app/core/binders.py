"""Binder/bitumen grade master list — loaded from app/data/binder_grades.json.

Simple registry; no compliance math. Used by the project form combo and the
Word report header.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BinderGrade:
    code: str
    full_name: str
    default_sg: float = 1.0
    applicable_tests: tuple[str, ...] = ()
    category: str = "neat"


# Property labels used by the UI + Word report.  Order matters (display order).
PROPERTY_LABELS: dict[str, str] = {
    "specific_gravity":   "Specific Gravity",
    "penetration":        "Penetration @25°C (1/10 mm)",
    "softening_point":    "Softening Point (°C)",
    "ductility":          "Ductility @27°C (cm)",
    "viscosity":          "Viscosity @60°C (Poise)",
    "flash_point":        "Flash Point (°C)",
    "elastic_recovery":   "Elastic Recovery (%)",
    "residue_pct":        "Residue by Distillation (%)",
    "storage_stability":  "Storage Stability (24h, %)",
    "particle_charge":    "Particle Charge",
    "expansion_ratio":    "Expansion Ratio",
    "half_life":          "Half-life (s)",
}


_FALLBACK: tuple[BinderGrade, ...] = (
    BinderGrade("VG-30", "VG-30 (IS 73)", 1.01,
                ("specific_gravity", "penetration", "softening_point",
                 "ductility", "viscosity", "flash_point"), "neat"),
    BinderGrade("Custom", "Custom / User-defined", 1.00,
                ("specific_gravity",), "custom"),
)


def _binders_json_path() -> Path:
    try:
        from app.config import APP_DIR, USER_DATA_DIR
    except ImportError:
        return Path(__file__).resolve().parents[1] / "data" / "binder_grades.json"
    user = USER_DATA_DIR / "binder_grades.json"
    if user.exists():
        return user
    return APP_DIR / "data" / "binder_grades.json"


def load_binders() -> dict[str, BinderGrade]:
    path = _binders_json_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out: dict[str, BinderGrade] = {}
        for g in data.get("grades", []):
            out[g["code"]] = BinderGrade(
                code=g["code"],
                full_name=g.get("full_name", g["code"]),
                default_sg=float(g.get("default_sg", 1.0)),
                applicable_tests=tuple(g.get("applicable_tests", ())),
                category=g.get("category", "neat"),
            )
        if not out:
            raise ValueError("No binder grades in JSON.")
        return out
    except Exception as e:                                          # pragma: no cover
        log.warning("Falling back to hardcoded binder grades (reason: %s)", e)
        return {b.code: b for b in _FALLBACK}


BINDER_GRADES: dict[str, BinderGrade] = load_binders()


def reload_binders() -> int:
    BINDER_GRADES.clear()
    BINDER_GRADES.update(load_binders())
    return len(BINDER_GRADES)
