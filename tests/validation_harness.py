"""Phase-16 validation harness.

Runs the full engineering pipeline (condition -> traffic -> structural ->
mechanistic -> rehab) for each canonical sample project under
``app/data/sample_projects/`` and asserts:

  * fast-fail engineering intent declared inline in each sample's
    ``expected`` block (PCI band, MSA band, refused flag, verdict
    strings, rehab category must-include / must-exclude sets);
  * full deterministic snapshot equality against the golden file at
    ``tests/golden/sample_projects/<name>.expected.json``.

Snapshots are intentionally CATEGORY-LEVEL (PCI band, MSA band,
verdict string, sorted rehab category set, layer count, thickness
band) — never raw float equality, because every calibration constant
in the engine is currently flagged ``IRC37_PLACEHOLDER`` /
``placeholder``.

Bless mode
----------
Set ``PAVEMENT_LAB_BLESS_GOLDENS=1`` in the environment to (re)write
golden snapshots from the current pipeline output instead of asserting
against them. CI / pytest never run in bless mode — assertions only.

CLI
---
    python -m tests.validation_harness                  # validate all
    python -m tests.validation_harness <name>           # validate one
    PAVEMENT_LAB_BLESS_GOLDENS=1 python -m tests.validation_harness  # bless
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from app.core import (
    ConditionSurveyInput,
    ConditionSurveyResult,
    DistressRecord,
    FatigueCalibration,
    IITPavePavementLayer,
    IITPavePointResult,
    LABEL_FATIGUE,
    LABEL_RUTTING,
    MechanisticResult,
    MechanisticValidationInput,
    MechanisticValidationSummary,
    PavementStructure,
    RecommendationContext,
    RehabSynthesisResult,
    RehabThresholds,
    RuttingCalibration,
    StructuralInput,
    StructuralResult,
    TrafficInput,
    TrafficResult,
    compute_condition_survey,
    compute_mechanistic_validation,
    compute_rehab_recommendations,
    compute_structural_design,
    compute_traffic_analysis,
    get_fatigue_calibration,
    get_rehab_thresholds,
    get_rutting_calibration,
    set_fatigue_calibration,
    set_rehab_thresholds,
    set_rutting_calibration,
)
from app.core.code_refs import CodeRef
from app.data.sample_projects import list_samples, load_sample, sample_dir


# ---------------------------------------------------------------------------
# Banding helpers (deterministic; never raw floats)
# ---------------------------------------------------------------------------

def _msa_band(msa: float) -> str:
    if msa <= 1.0:
        return "very_low"
    if msa <= 5.0:
        return "low"
    if msa <= 30.0:
        return "mid"
    return "heavy"


def _thickness_band(t_mm: float) -> str:
    if t_mm < 300:
        return "thin"
    if t_mm <= 500:
        return "medium"
    return "thick"


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _build_distress_records(records: list[Mapping]) -> tuple[DistressRecord, ...]:
    return tuple(
        DistressRecord(
            distress_type=r.get("distress_type", "cracking"),
            severity=r.get("severity", "low"),
            length_m=float(r.get("length_m", 0.0) or 0.0),
            area_m2=float(r.get("area_m2", 0.0) or 0.0),
            count=int(r.get("count", 0) or 0),
            notes=r.get("notes", "") or "",
        )
        for r in records or ()
    )


def _build_structure(blob: Mapping) -> PavementStructure:
    layers = []
    for layer in blob.get("layers") or ():
        thickness = layer.get("thickness_mm")
        layers.append(IITPavePavementLayer(
            name=layer.get("name", ""),
            material=layer.get("material", ""),
            modulus_mpa=float(layer.get("modulus_mpa", 1.0)),
            poisson_ratio=float(layer.get("poisson_ratio", 0.35)),
            thickness_mm=None if thickness is None else float(thickness),
        ))
    return PavementStructure(layers=tuple(layers))


def _synth_mech_result(mech_blob: Mapping) -> MechanisticResult:
    eps_t = float(mech_blob["epsilon_t_microstrain"])
    eps_v = float(mech_blob["epsilon_v_microstrain"])
    bt = IITPavePointResult(
        z_mm=120.0, r_mm=0.0,
        sigma_z_mpa=0.5, sigma_r_mpa=0.1, sigma_t_mpa=0.1,
        epsilon_z_microstrain=-eps_t,
        epsilon_r_microstrain=eps_t,
        epsilon_t_microstrain=eps_t,
    )
    sg = IITPavePointResult(
        z_mm=320.0, r_mm=0.0,
        sigma_z_mpa=0.05, sigma_r_mpa=0.01, sigma_t_mpa=0.01,
        epsilon_z_microstrain=eps_v,
        epsilon_r_microstrain=-eps_v * 0.3,
        epsilon_t_microstrain=-eps_v * 0.3,
    )
    return MechanisticResult(
        point_results=(bt, sg),
        references=(CodeRef("IRC:37-2018", "cl. 6.2",
                            "Multi-layered elastic analysis"),),
        is_placeholder=bool(mech_blob.get("is_placeholder", True)),
        source=mech_blob.get("source", "stub"),
    )


@dataclass(frozen=True, slots=True)
class _Pipeline:
    sample: Mapping
    condition: ConditionSurveyResult
    traffic: TrafficResult
    structural: StructuralResult
    mechanistic: Optional[MechanisticValidationSummary]
    rehab: RehabSynthesisResult


def _apply_calibration_overrides(blob: Mapping) -> tuple:
    """Apply any sample-supplied calibration overrides; return the
    PRIOR values so the caller can restore them in a finally block.

    Always returns a 3-tuple (rehab, fatigue, rutting); each entry is
    None if no override was applied to that calibration.
    """
    overrides = blob or {}
    prev_rehab = prev_fatigue = prev_rutting = None
    rehab_o = overrides.get("rehab_thresholds")
    if rehab_o:
        prev_rehab = get_rehab_thresholds()
        set_rehab_thresholds(RehabThresholds(
            label=rehab_o.get("label", "sample-override"),
            pci_excellent_min=float(rehab_o["pci_excellent_min"]),
            pci_good_min=float(rehab_o["pci_good_min"]),
            pci_fair_min=float(rehab_o["pci_fair_min"]),
            pci_poor_min=float(rehab_o["pci_poor_min"]),
            msa_low_max=float(rehab_o["msa_low_max"]),
            msa_mid_max=float(rehab_o["msa_mid_max"]),
            ravelling_area_m2_min=float(rehab_o.get("ravelling_area_m2_min", 50.0)),
            bleeding_area_m2_min=float(rehab_o.get("bleeding_area_m2_min", 50.0)),
            is_placeholder=True,
        ))
    fat_o = overrides.get("fatigue_calibration")
    if fat_o:
        prev_fatigue = get_fatigue_calibration()
        set_fatigue_calibration(FatigueCalibration(
            label=fat_o.get("label", "sample-override"),
            k1=float(fat_o["k1"]),
            k2=float(fat_o["k2"]),
            k3=float(fat_o["k3"]),
            reliability_pct=int(fat_o.get("reliability_pct", 80)),
            is_placeholder=True,
        ))
    rut_o = overrides.get("rutting_calibration")
    if rut_o:
        prev_rutting = get_rutting_calibration()
        set_rutting_calibration(RuttingCalibration(
            label=rut_o.get("label", "sample-override"),
            k_r=float(rut_o["k_r"]),
            k_v=float(rut_o["k_v"]),
            reliability_pct=int(rut_o.get("reliability_pct", 80)),
            is_placeholder=True,
        ))
    return prev_rehab, prev_fatigue, prev_rutting


def _restore_calibration(prev: tuple) -> None:
    prev_rehab, prev_fatigue, prev_rutting = prev
    if prev_rehab is not None:
        set_rehab_thresholds(prev_rehab)
    if prev_fatigue is not None:
        set_fatigue_calibration(prev_fatigue)
    if prev_rutting is not None:
        set_rutting_calibration(prev_rutting)


def run_pipeline(sample: Mapping) -> _Pipeline:
    """Apply calibration overrides, run pipeline, ALWAYS restore."""
    prev = _apply_calibration_overrides(sample.get("calibration_overrides") or {})
    try:
        cond_blob = sample["condition"]
        cond_in = ConditionSurveyInput(
            work_name=cond_blob.get("work_name", "") or "",
            surveyed_by=cond_blob.get("surveyed_by", "") or "",
            survey_date=cond_blob.get("survey_date", "") or "",
            chainage_from_km=float(cond_blob.get("chainage_from_km", 0.0) or 0.0),
            chainage_to_km=float(cond_blob.get("chainage_to_km", 0.0) or 0.0),
            lane_id=cond_blob.get("lane_id", "") or "",
            records=_build_distress_records(cond_blob.get("records") or ()),
        )
        cond_result = compute_condition_survey(cond_in)

        tr_blob = sample["traffic"]
        traffic_result = compute_traffic_analysis(TrafficInput(
            initial_cvpd=float(tr_blob["initial_cvpd"]),
            growth_rate_pct=float(tr_blob["growth_rate_pct"]),
            design_life_years=int(tr_blob["design_life_years"]),
            terrain=tr_blob.get("terrain", "Plain"),
            lane_config=tr_blob.get("lane_config", "Two-lane carriageway"),
            road_category=tr_blob.get("road_category", "NH / SH"),
        ))

        st_blob = sample["structural"]
        structural_result = compute_structural_design(StructuralInput(
            road_category=st_blob.get("road_category", "NH / SH"),
            design_life_years=int(st_blob["design_life_years"]),
            initial_cvpd=float(st_blob["initial_cvpd"]),
            growth_rate_pct=float(st_blob["growth_rate_pct"]),
            vdf=float(st_blob["vdf"]),
            ldf=float(st_blob["ldf"]),
            subgrade_cbr_pct=float(st_blob["subgrade_cbr_pct"]),
        ))

        mech_summary: Optional[MechanisticValidationSummary] = None
        mech_blob = sample.get("mechanistic") or {}
        if mech_blob.get("include", False):
            structure = _build_structure(mech_blob.get("structure") or {})
            mech_result = _synth_mech_result(mech_blob)
            design_msa_override = mech_blob.get("design_msa_override")
            design_msa = (float(design_msa_override)
                          if design_msa_override is not None
                          else float(traffic_result.design_msa))
            mech_summary = compute_mechanistic_validation(
                MechanisticValidationInput(
                    mech_result=mech_result,
                    structure=structure,
                    design_msa=design_msa,
                    c_factor=float(mech_blob.get("c_factor", 1.0)),
                    point_labels=(LABEL_FATIGUE, LABEL_RUTTING),
                )
            )

        rehab_result = compute_rehab_recommendations(RecommendationContext(
            condition=cond_result,
            traffic=traffic_result,
        ))

        return _Pipeline(
            sample=sample,
            condition=cond_result,
            traffic=traffic_result,
            structural=structural_result,
            mechanistic=mech_summary,
            rehab=rehab_result,
        )
    finally:
        _restore_calibration(prev)


# ---------------------------------------------------------------------------
# Snapshot extraction (CATEGORY-LEVEL, never raw floats)
# ---------------------------------------------------------------------------

def build_snapshot(p: _Pipeline) -> dict[str, Any]:
    sample = p.sample
    snapshot: dict[str, Any] = {
        "name": sample["name"],
        "condition": {
            "pci_band": p.condition.condition_category,
            "distress_record_count": len(p.condition.inputs.records),
            "is_placeholder": bool(p.condition.is_placeholder),
        },
        "traffic": {
            "msa_band": _msa_band(p.traffic.design_msa),
            "traffic_category": p.traffic.traffic_category,
        },
        "structural": {
            "layer_count": len(p.structural.composition),
            "thickness_band": _thickness_band(
                p.structural.total_pavement_thickness_mm),
        },
        "rehab": {
            "categories": sorted(r.category for r in p.rehab.recommendations),
            "category_count": len(p.rehab.recommendations),
            "is_placeholder": bool(p.rehab.is_placeholder),
        },
    }
    if p.mechanistic is not None:
        snapshot["mechanistic"] = {
            "refused": bool(p.mechanistic.refused),
            "is_placeholder": bool(p.mechanistic.is_placeholder),
            "fatigue_verdict": p.mechanistic.fatigue.verdict,
            "rutting_verdict": p.mechanistic.rutting.verdict,
        }
    else:
        snapshot["mechanistic"] = None
    return snapshot


# ---------------------------------------------------------------------------
# Fast-fail assertions from the sample's "expected" block
# ---------------------------------------------------------------------------

def _expected_assert(sample: Mapping, snapshot: Mapping) -> list[str]:
    """Return list of human-readable failure messages (empty == OK)."""
    expected = sample.get("expected") or {}
    failures: list[str] = []

    cond = expected.get("condition") or {}
    if "pci_band" in cond and cond["pci_band"] != snapshot["condition"]["pci_band"]:
        failures.append(
            f"condition.pci_band: expected {cond['pci_band']!r}, "
            f"got {snapshot['condition']['pci_band']!r}")

    tr = expected.get("traffic") or {}
    if "msa_band" in tr and tr["msa_band"] != snapshot["traffic"]["msa_band"]:
        failures.append(
            f"traffic.msa_band: expected {tr['msa_band']!r}, "
            f"got {snapshot['traffic']['msa_band']!r}")

    mech = expected.get("mechanistic")
    if mech and snapshot.get("mechanistic"):
        for k in ("refused", "fatigue_verdict", "rutting_verdict"):
            if k in mech and mech[k] != snapshot["mechanistic"][k]:
                failures.append(
                    f"mechanistic.{k}: expected {mech[k]!r}, "
                    f"got {snapshot['mechanistic'][k]!r}")

    rh = expected.get("rehab") or {}
    cats_actual = set(snapshot["rehab"]["categories"])
    for inc in (rh.get("categories_must_include") or ()):
        if inc not in cats_actual:
            failures.append(
                f"rehab.categories: missing required {inc!r} "
                f"(got {sorted(cats_actual)})")
    for exc in (rh.get("categories_must_exclude") or ()):
        if exc in cats_actual:
            failures.append(
                f"rehab.categories: forbidden {exc!r} present "
                f"(got {sorted(cats_actual)})")

    return failures


# ---------------------------------------------------------------------------
# Golden snapshot I/O
# ---------------------------------------------------------------------------

GOLDEN_DIR: Path = (
    Path(__file__).resolve().parent / "golden" / "sample_projects"
)
BLESS_ENV: str = "PAVEMENT_LAB_BLESS_GOLDENS"


def _golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.expected.json"


def _bless_mode() -> bool:
    return os.environ.get(BLESS_ENV) == "1"


def validate_sample(name: str) -> None:
    """Run the pipeline for ``name`` and assert / bless the snapshot.

    Raises ``AssertionError`` on mismatch (not in bless mode).
    """
    sample = load_sample(name)
    pipeline = run_pipeline(sample)
    snapshot = build_snapshot(pipeline)

    # Engineering-intent fast-fail.
    failures = _expected_assert(sample, snapshot)
    if failures:
        raise AssertionError(
            f"[{name}] sample 'expected' block mismatched:\n  - "
            + "\n  - ".join(failures)
        )

    # Golden snapshot.
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    gp = _golden_path(name)
    if _bless_mode() or not gp.exists():
        gp.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return

    expected = json.loads(gp.read_text(encoding="utf-8"))
    if expected != snapshot:
        # Build a compact diff.
        diff_lines: list[str] = []
        for k in sorted(set(expected) | set(snapshot)):
            if expected.get(k) != snapshot.get(k):
                diff_lines.append(
                    f"  - {k}: expected={expected.get(k)!r} "
                    f"got={snapshot.get(k)!r}"
                )
        raise AssertionError(
            f"[{name}] golden snapshot mismatch (set "
            f"{BLESS_ENV}=1 to re-bless):\n" + "\n".join(diff_lines)
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    names = argv if argv else list(list_samples())
    if not names:
        print(f"No sample projects found under {sample_dir()}", file=sys.stderr)
        return 1
    bless = _bless_mode()
    print(f"=== Phase-16 validation harness ({'BLESS' if bless else 'ASSERT'} mode) ===")
    print(f"  sample_dir: {sample_dir()}")
    print(f"  golden_dir: {GOLDEN_DIR}")
    failed: list[tuple[str, str]] = []
    for name in names:
        try:
            validate_sample(name)
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed.append((name, str(e)))
            print(f"  [FAIL] {name}\n{e}")
        except Exception as e:  # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    if failed:
        print(f"\nVALIDATION HARNESS: {len(failed)}/{len(names)} FAILED")
        return 1
    print(f"\nVALIDATION HARNESS: {len(names)} sample(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
