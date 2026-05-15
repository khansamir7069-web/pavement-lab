"""Phase-12 rehab synthesis smoke.

Pure-Python, no Qt, no DB, no filesystem — exercises only the new
``app.core.rehab_engine`` module against synthetic ConditionSurveyResult
and TrafficResult fixtures.

Coverage:

  1. Empty / excellent survey -> ROUTINE_MAINTENANCE only.
  2. Survey with potholes + high-severity cracking -> POTHOLE_PATCHING
     and OVERLAY both present (CRACK_SEALING suppressed for high-severity).
  3. Fair PCI with no traffic data -> SLURRY_SEAL present, MICRO_SURFACING
     absent.
  4. Fair PCI with mid-range MSA -> MICRO_SURFACING present, SLURRY_SEAL
     absent.
  5. Heavy traffic (MSA > mid threshold) -> OVERLAY present even on
     mid-range PCI.
  6. PCI < 40 -> RECONSTRUCTION present + flagged placeholder.
  7. Surface distress (ravelling/bleeding low-medium) -> SURFACE_TREATMENT.
  8. References on every recommendation are CodeRef instances tagged
     IRC/MoRTH.
  9. ``set_thresholds`` swap retunes the engine (raise pci_excellent_min
     so a previously-routine survey no longer triggers).
"""
from __future__ import annotations

from app.core import (
    ConditionSurveyInput,
    DistressRecord,
    RecommendationContext,
    RehabThresholds,
    TREATMENT_CATEGORIES,
    TC_CRACK_SEALING,
    TC_MICRO_SURFACING,
    TC_OVERLAY,
    TC_POTHOLE_PATCHING,
    TC_RECONSTRUCTION,
    TC_ROUTINE_MAINTENANCE,
    TC_SLURRY_SEAL,
    TC_SURFACE_TREATMENT,
    TrafficInput,
    compute_condition_survey,
    compute_rehab_recommendations,
    compute_traffic_analysis,
    get_rehab_thresholds,
    reset_rehab_thresholds,
    set_rehab_thresholds,
)
from app.core.code_refs import CodeRef


def _condition(records=()):
    return compute_condition_survey(ConditionSurveyInput(records=tuple(records)))


def _traffic(cvpd: float, growth: float = 5.0, life: int = 15):
    return compute_traffic_analysis(TrafficInput(
        initial_cvpd=cvpd,
        growth_rate_pct=growth,
        design_life_years=life,
        terrain="Plain",
        lane_config="Two-lane carriageway",
    ))


def _cats(result) -> set[str]:
    return {r.category for r in result.recommendations}


def main() -> int:
    print("=== 1) Excellent / empty survey ===")
    r = compute_rehab_recommendations(RecommendationContext(condition=_condition()))
    assert _cats(r) == {TC_ROUTINE_MAINTENANCE}, _cats(r)
    assert r.is_placeholder is True
    assert r.recommendations[0].priority == 5
    print(f"  [PASS] only {TC_ROUTINE_MAINTENANCE}; summary={r.context_summary!r}")

    print("\n=== 2) Potholes + high-severity cracking ===")
    cond2 = _condition([
        DistressRecord("potholes", "medium", count=3),
        DistressRecord("cracking", "high", length_m=150.0),
    ])
    r2 = compute_rehab_recommendations(RecommendationContext(condition=cond2))
    cats2 = _cats(r2)
    assert TC_POTHOLE_PATCHING in cats2
    assert TC_OVERLAY in cats2
    assert TC_CRACK_SEALING not in cats2, "high-severity cracking must not trigger crack_sealing"
    # Priority sort -> safety (1) before structural (2)
    ordered = [r.category for r in r2.recommendations]
    assert ordered.index(TC_POTHOLE_PATCHING) <= ordered.index(TC_OVERLAY)
    print(f"  [PASS] cats={cats2}")

    print("\n=== 3) Fair PCI + no traffic data -> slurry seal ===")
    # Sized to drop PCI into Fair (55-69). Deduct math under the
    # placeholder calibration: rutting medium 80 m^2 = 3.0*1.5*(80/10) = 36
    # plus cracking low 80 m = 1.0*1.2*(80/100) = 0.96 -> PCI ~63.
    cond3 = _condition([
        DistressRecord("rutting", "medium", area_m2=80.0),
        DistressRecord("cracking", "low", length_m=80.0),
        DistressRecord("ravelling", "low", area_m2=20.0),
    ])
    pci3 = cond3.pci_score
    assert 55.0 <= pci3 < 70.0, f"fixture PCI not in Fair: {pci3}"
    r3 = compute_rehab_recommendations(RecommendationContext(condition=cond3))
    cats3 = _cats(r3)
    assert TC_SLURRY_SEAL in cats3, cats3
    assert TC_MICRO_SURFACING not in cats3, cats3
    print(f"  [PASS] PCI={pci3:.1f} cats={cats3}")

    print("\n=== 4) Fair PCI + mid-range MSA -> micro surfacing ===")
    traffic_mid = _traffic(cvpd=800)  # ~12 MSA under default presets
    assert 5.0 < traffic_mid.design_msa <= 30.0, traffic_mid.design_msa
    r4 = compute_rehab_recommendations(RecommendationContext(
        condition=cond3, traffic=traffic_mid,
    ))
    cats4 = _cats(r4)
    assert TC_MICRO_SURFACING in cats4, cats4
    assert TC_SLURRY_SEAL not in cats4, cats4
    print(f"  [PASS] MSA={traffic_mid.design_msa:.2f} cats={cats4}")

    print("\n=== 5) Heavy traffic (MSA > mid threshold) -> overlay ===")
    traffic_heavy = _traffic(cvpd=10_000)
    assert traffic_heavy.design_msa > 30.0, traffic_heavy.design_msa
    r5 = compute_rehab_recommendations(RecommendationContext(
        condition=cond3, traffic=traffic_heavy,
    ))
    cats5 = _cats(r5)
    assert TC_OVERLAY in cats5
    print(f"  [PASS] MSA={traffic_heavy.design_msa:.2f} cats={cats5}")

    print("\n=== 6) PCI < 40 -> reconstruction ===")
    cond6 = _condition([
        DistressRecord("potholes", "high", count=200),
        DistressRecord("cracking", "high", length_m=2000.0),
    ])
    pci6 = cond6.pci_score
    assert pci6 < 40.0, f"fixture PCI not below poor_min: {pci6}"
    r6 = compute_rehab_recommendations(RecommendationContext(condition=cond6))
    cats6 = _cats(r6)
    assert TC_RECONSTRUCTION in cats6
    recon = next(r for r in r6.recommendations if r.category == TC_RECONSTRUCTION)
    assert recon.is_placeholder is True
    assert "PLACEHOLDER" in recon.reason
    print(f"  [PASS] PCI={pci6:.1f} cats={cats6}")

    print("\n=== 7) Surface distress -> surface treatment ===")
    cond7 = _condition([
        DistressRecord("ravelling", "medium", area_m2=30.0),
        DistressRecord("bleeding", "low", area_m2=10.0),
    ])
    r7 = compute_rehab_recommendations(RecommendationContext(condition=cond7))
    cats7 = _cats(r7)
    assert TC_SURFACE_TREATMENT in cats7, cats7
    print(f"  [PASS] cats={cats7}")

    print("\n=== 8) References + next_module hints ===")
    for rec in r2.recommendations + r4.recommendations + r5.recommendations + r6.recommendations:
        assert rec.references, f"empty references on {rec.category}"
        for ref in rec.references:
            assert isinstance(ref, CodeRef)
            assert ref.code_id, f"missing code_id on {rec.category}"
        assert rec.next_module in (
            "none", "maintenance.overlay", "maintenance.cold_mix",
            "maintenance.micro_surfacing", "structural_design",
        ), rec.next_module
        # priority is a known bucket
        assert 1 <= rec.priority <= 5
    # Every category constant is in the canonical tuple.
    for c in (TC_ROUTINE_MAINTENANCE, TC_CRACK_SEALING, TC_POTHOLE_PATCHING,
              TC_SURFACE_TREATMENT, TC_SLURRY_SEAL, TC_MICRO_SURFACING,
              TC_OVERLAY, TC_RECONSTRUCTION):
        assert c in TREATMENT_CATEGORIES
    print("  [PASS] every recommendation has CodeRef refs + valid next_module")

    print("\n=== 9) Threshold swap retunes the engine ===")
    base = get_rehab_thresholds()
    assert base.is_placeholder is True
    # Raise the excellent threshold past PCI=100 — routine_maintenance can
    # no longer fire on an empty survey.
    hot = RehabThresholds(
        pci_excellent_min=101.0,
        pci_good_min=base.pci_good_min,
        pci_fair_min=base.pci_fair_min,
        pci_poor_min=base.pci_poor_min,
        msa_low_max=base.msa_low_max,
        msa_mid_max=base.msa_mid_max,
        label="smoke-test-impossible-excellent",
    )
    set_rehab_thresholds(hot)
    r_after = compute_rehab_recommendations(RecommendationContext(condition=_condition()))
    assert TC_ROUTINE_MAINTENANCE not in _cats(r_after), _cats(r_after)
    reset_rehab_thresholds()
    r_reset = compute_rehab_recommendations(RecommendationContext(condition=_condition()))
    assert TC_ROUTINE_MAINTENANCE in _cats(r_reset)
    # Per-call override (independent of module state)
    r_call_override = compute_rehab_recommendations(
        RecommendationContext(condition=_condition()),
        thresholds=hot,
    )
    assert TC_ROUTINE_MAINTENANCE not in _cats(r_call_override)
    print("  [PASS] thresholds swap via set_thresholds AND per-call override both honoured")

    print("\nPHASE 12 REHAB SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
