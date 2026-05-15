"""MoRTH-spec compliance checks per mix type.

The ``MIX_SPECS`` dict and ``MIX_TYPES`` registry are populated at import-time
from ``app/data/mix_specs.json``.  If the JSON file is missing or unreadable,
the hardcoded fallback at the bottom of this module is used (so the engine
and parity tests always work).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MixSpec:
    name: str                       # e.g. "DBM Grade II"
    stability_min_kn: float
    flow_min_mm: float
    flow_max_mm: float
    air_voids_min_pct: float
    air_voids_max_pct: float
    vma_min_pct: float
    vfb_min_pct: float
    vfb_max_pct: float
    marshall_quotient_min: float
    marshall_quotient_max: float
    compaction_blows_each_face: int
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CheckItem:
    name: str
    value: float
    requirement: str
    pass_: bool


@dataclass(frozen=True, slots=True)
class ComplianceResult:
    spec_name: str
    items: tuple[CheckItem, ...]
    overall_pass: bool


@dataclass(frozen=False, slots=True)
class MixTypeRecord:
    """Full metadata for a single mix type loaded from mix_specs.json."""
    mix_code: str
    full_name: str
    category: str                  # hot_mix | surface_course | maintenance | recycling
    layer_type: str = ""
    applicable_code: str = ""
    nmas_mm: float | None = None
    sieve_sizes_mm: tuple[float, ...] = ()
    gradation_lower: tuple[float | None, ...] = ()
    gradation_upper: tuple[float | None, ...] = ()
    binder_grades: tuple[str, ...] = ()
    trial_pb_min: float | None = None
    trial_pb_max: float | None = None
    marshall: dict | None = None    # raw dict; None for non-Marshall types
    report_template: str = ""
    status: str = "placeholder_editable"
    notes: str = ""


_FALLBACK_MIX_SPECS: dict[str, MixSpec] = {
    "DBM-I": MixSpec(
        name="DBM Grade I",
        stability_min_kn=9.0,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=14.0,
        vfb_min_pct=65.0, vfb_max_pct=78.0,
        marshall_quotient_min=2.0, marshall_quotient_max=5.0,
        compaction_blows_each_face=75,
        notes="MoRTH 500-9: DBM Grade I, NMAS 26.5 mm",
    ),
    "DBM-II": MixSpec(
        name="DBM Grade II",
        stability_min_kn=9.0,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=13.25,
        vfb_min_pct=65.0, vfb_max_pct=75.0,
        marshall_quotient_min=2.0, marshall_quotient_max=5.0,
        compaction_blows_each_face=75,
        notes="MoRTH 500-10: DBM Grade II, NMAS 19 mm",
    ),
    "BC-I": MixSpec(
        name="Bituminous Concrete Grade I",
        stability_min_kn=9.0,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=14.0,
        vfb_min_pct=65.0, vfb_max_pct=78.0,
        marshall_quotient_min=2.0, marshall_quotient_max=5.0,
        compaction_blows_each_face=75,
        notes="MoRTH 500-17: BC Grade I, NMAS 19 mm",
    ),
    "BC-II": MixSpec(
        name="Bituminous Concrete Grade II",
        stability_min_kn=9.0,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=14.0,
        vfb_min_pct=65.0, vfb_max_pct=78.0,
        marshall_quotient_min=2.0, marshall_quotient_max=5.0,
        compaction_blows_each_face=75,
        notes="MoRTH 500-17: BC Grade II, NMAS 13.2 mm",
    ),
    "SDAC": MixSpec(
        name="Semi-Dense Asphaltic Concrete",
        stability_min_kn=8.2,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=12.0,
        vfb_min_pct=65.0, vfb_max_pct=78.0,
        marshall_quotient_min=2.0, marshall_quotient_max=6.0,
        compaction_blows_each_face=75,
        notes="MoRTH 500-15: SDAC, NMAS 13.2 mm",
    ),
    "BM": MixSpec(
        name="Bituminous Macadam",
        stability_min_kn=3.4,
        flow_min_mm=2.0, flow_max_mm=4.0,
        air_voids_min_pct=3.0, air_voids_max_pct=5.0,
        vma_min_pct=12.0,
        vfb_min_pct=65.0, vfb_max_pct=78.0,
        marshall_quotient_min=2.0, marshall_quotient_max=6.0,
        compaction_blows_each_face=50,
        notes="MoRTH 500-3: BM, open-graded base course",
    ),
}


# ---------------------------------------------------------------------------
# JSON-backed specification registry
# ---------------------------------------------------------------------------

def _specs_json_path() -> Path:
    """Locate mix_specs.json — prefer user override, fall back to bundled."""
    try:
        from app.config import APP_DIR, USER_DATA_DIR
    except ImportError:
        return Path(__file__).resolve().parents[1] / "data" / "mix_specs.json"
    user_copy = USER_DATA_DIR / "mix_specs.json"
    if user_copy.exists():
        return user_copy
    return APP_DIR / "data" / "mix_specs.json"


def _build_mixspec_from_dict(code: str, full_name: str, m: dict, notes: str) -> MixSpec:
    return MixSpec(
        name=full_name,
        stability_min_kn=float(m["stability_min_kn"]),
        flow_min_mm=float(m["flow_min_mm"]),
        flow_max_mm=float(m["flow_max_mm"]),
        air_voids_min_pct=float(m["air_voids_min_pct"]),
        air_voids_max_pct=float(m["air_voids_max_pct"]),
        vma_min_pct=float(m["vma_min_pct"]),
        vfb_min_pct=float(m["vfb_min_pct"]),
        vfb_max_pct=float(m["vfb_max_pct"]),
        marshall_quotient_min=float(m["marshall_quotient_min"]),
        marshall_quotient_max=float(m["marshall_quotient_max"]),
        compaction_blows_each_face=int(m["compaction_blows_each_face"]),
        notes=notes,
    )


def _record_from_dict(d: dict) -> MixTypeRecord:
    def _t(key, default=()):
        v = d.get(key, default)
        return tuple(v) if v is not None else ()
    return MixTypeRecord(
        mix_code=d["mix_code"],
        full_name=d.get("full_name", d["mix_code"]),
        category=d.get("category", "hot_mix"),
        layer_type=d.get("layer_type", ""),
        applicable_code=d.get("applicable_code", ""),
        nmas_mm=d.get("nmas_mm"),
        sieve_sizes_mm=_t("sieve_sizes_mm"),
        gradation_lower=_t("gradation_lower"),
        gradation_upper=_t("gradation_upper"),
        binder_grades=_t("binder_grades"),
        trial_pb_min=d.get("trial_pb_min"),
        trial_pb_max=d.get("trial_pb_max"),
        marshall=d.get("marshall"),
        report_template=d.get("report_template", ""),
        status=d.get("status", "placeholder_editable"),
        notes=d.get("notes", ""),
    )


def _load_specs_from_json() -> tuple[dict[str, MixSpec], dict[str, MixTypeRecord]]:
    """Parse mix_specs.json. On any error, return the hardcoded fallback."""
    path = _specs_json_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        specs: dict[str, MixSpec] = {}
        records: dict[str, MixTypeRecord] = {}
        for entry in data.get("mix_types", []):
            rec = _record_from_dict(entry)
            records[rec.mix_code] = rec
            if entry.get("marshall"):
                specs[rec.mix_code] = _build_mixspec_from_dict(
                    rec.mix_code, rec.full_name, entry["marshall"], rec.notes
                )
        if not specs:
            raise ValueError("No Marshall-compliant mix types found in JSON.")
        return specs, records
    except Exception as e:                                       # pragma: no cover
        log.warning("Falling back to hardcoded MIX_SPECS (reason: %s)", e)
        # Build minimal MixTypeRecord set for the fallback
        recs = {
            code: MixTypeRecord(
                mix_code=code,
                full_name=spec.name,
                category="hot_mix",
                marshall={"_legacy": True},
                status="verified",
                notes=spec.notes,
            )
            for code, spec in _FALLBACK_MIX_SPECS.items()
        }
        return dict(_FALLBACK_MIX_SPECS), recs


# Public globals — mutated in place by reload_specs() so existing imports stay valid.
MIX_SPECS: dict[str, MixSpec] = {}
MIX_TYPES: dict[str, MixTypeRecord] = {}


def reload_specs() -> tuple[int, int]:
    """Re-read mix_specs.json and update MIX_SPECS / MIX_TYPES in place.

    Returns (n_marshall_specs, n_total_types).
    """
    specs, records = _load_specs_from_json()
    MIX_SPECS.clear(); MIX_SPECS.update(specs)
    MIX_TYPES.clear(); MIX_TYPES.update(records)
    return len(specs), len(records)


def save_specs(records: dict[str, MixTypeRecord], path: Path | None = None) -> Path:
    """Write a registry back to JSON (user-data folder by default).

    Only saved Marshall values are merged back; other metadata is preserved
    from the existing file.  Returns the path written.
    """
    try:
        from app.config import USER_DATA_DIR
        target = path or (USER_DATA_DIR / "mix_specs.json")
    except ImportError:
        target = path or _specs_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Load existing file as base, then merge edits
    base = {"_meta": {}, "mix_types": []}
    src = _specs_json_path()
    if src.exists():
        try:
            base = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            pass
    by_code = {e["mix_code"]: e for e in base.get("mix_types", [])}
    for code, rec in records.items():
        entry = by_code.get(code, {"mix_code": code})
        entry.update({
            "mix_code": rec.mix_code,
            "full_name": rec.full_name,
            "category": rec.category,
            "layer_type": rec.layer_type,
            "applicable_code": rec.applicable_code,
            "nmas_mm": rec.nmas_mm,
            "sieve_sizes_mm": list(rec.sieve_sizes_mm) or None,
            "gradation_lower": list(rec.gradation_lower) or None,
            "gradation_upper": list(rec.gradation_upper) or None,
            "binder_grades": list(rec.binder_grades),
            "trial_pb_min": rec.trial_pb_min,
            "trial_pb_max": rec.trial_pb_max,
            "marshall": rec.marshall,
            "report_template": rec.report_template,
            "status": rec.status,
            "notes": rec.notes,
        })
        # Drop None-valued list keys for tidiness
        for k in ("sieve_sizes_mm", "gradation_lower", "gradation_upper"):
            if entry.get(k) is None:
                entry.pop(k, None)
        by_code[code] = entry
    base["mix_types"] = list(by_code.values())
    target.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return target


# Initial population at import time
reload_specs()


def check_compliance(
    spec_key: str,
    stability_kn: float,
    flow_mm: float,
    air_voids_pct: float,
    vma_pct: float,
    vfb_pct: float,
    marshall_quotient: float,
) -> ComplianceResult:
    spec = MIX_SPECS[spec_key]
    items = (
        CheckItem(
            name="Stability (kN)",
            value=stability_kn,
            requirement=f"≥ {spec.stability_min_kn}",
            pass_=stability_kn >= spec.stability_min_kn,
        ),
        CheckItem(
            name="Flow (mm)",
            value=flow_mm,
            requirement=f"{spec.flow_min_mm} – {spec.flow_max_mm}",
            pass_=spec.flow_min_mm <= flow_mm <= spec.flow_max_mm,
        ),
        CheckItem(
            name="Air Voids (%)",
            value=air_voids_pct,
            requirement=f"{spec.air_voids_min_pct} – {spec.air_voids_max_pct}",
            pass_=spec.air_voids_min_pct <= air_voids_pct <= spec.air_voids_max_pct,
        ),
        CheckItem(
            name="VMA (%)",
            value=vma_pct,
            requirement=f"≥ {spec.vma_min_pct}",
            pass_=vma_pct >= spec.vma_min_pct,
        ),
        CheckItem(
            name="VFB (%)",
            value=vfb_pct,
            requirement=f"{spec.vfb_min_pct} – {spec.vfb_max_pct}",
            pass_=spec.vfb_min_pct <= vfb_pct <= spec.vfb_max_pct,
        ),
        CheckItem(
            name="Marshall Quotient",
            value=marshall_quotient,
            requirement=f"{spec.marshall_quotient_min} – {spec.marshall_quotient_max}",
            pass_=spec.marshall_quotient_min <= marshall_quotient <= spec.marshall_quotient_max,
        ),
    )
    return ComplianceResult(
        spec_name=spec.name,
        items=items,
        overall_pass=all(i.pass_ for i in items),
    )
