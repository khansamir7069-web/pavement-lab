"""Phase-14 mechanistic-validation smoke.

Pure-Python, no Qt, no DB, no filesystem. Exercises only the new
``app.core.mechanistic_validation`` package against synthesized
``MechanisticResult`` fixtures.

Coverage:

  1. Refusal gate: a placeholder MechanisticResult (is_placeholder=True)
     produces a summary with refused=True, both verdicts None, both
     cumulative_life_msa None, and refused_reason citing placeholder.
  2. Non-placeholder mocked result yields verdicts (PASS or FAIL).
  3. PASS path: small strains + low design MSA -> PASS on both checks.
  4. FAIL path: large strains + high design MSA -> FAIL on both checks.
  5. Calibration swap: doubling fatigue k1 must increase fatigue life.
  6. Per-call calibration override is honoured.
  7. Strain-extraction fallback emits a non-empty warning that propagates
     into FatigueCheck.notes / RuttingCheck.notes (no silent substitution).
  8. Missing bituminous modulus -> fatigue refused with REFUSED_MISSING_E_BC.
  9. References on every Check are IRC:37 CodeRefs.
"""
from __future__ import annotations

from app.core import (
    DEFAULT_FATIGUE_CALIBRATION,
    FatigueCalibration,
    IITPavePavementLayer,
    IITPavePointResult,
    LABEL_FATIGUE,
    LABEL_RUTTING,
    MECH_VALIDATION_PLACEHOLDER_NOTE,
    MechanisticResult,
    MechanisticValidationInput,
    PavementStructure,
    REFUSED_MISSING_E_BC,
    REFUSED_PLACEHOLDER_MECH,
    compute_mechanistic_validation,
    get_fatigue_calibration,
    reset_fatigue_calibration,
    set_fatigue_calibration,
)
from app.core.code_refs import CodeRef


def _structure(e_bc_mpa: float = 3000.0) -> PavementStructure:
    return PavementStructure(layers=(
        IITPavePavementLayer(name="BC",  material="BC",  modulus_mpa=e_bc_mpa,
                             thickness_mm=40.0),
        IITPavePavementLayer(name="DBM", material="DBM", modulus_mpa=2500.0,
                             thickness_mm=80.0),
        IITPavePavementLayer(name="GSB", material="GSB", modulus_mpa=300.0,
                             thickness_mm=200.0),
        IITPavePavementLayer(name="Subgrade", material="Subgrade",
                             modulus_mpa=50.0, thickness_mm=None),
    ))


def _structure_no_bt() -> PavementStructure:
    """Granular-only stack (no BC/DBM/SMA) — fatigue must refuse."""
    return PavementStructure(layers=(
        IITPavePavementLayer(name="WBM", material="WBM", modulus_mpa=400.0,
                             thickness_mm=150.0),
        IITPavePavementLayer(name="GSB", material="GSB", modulus_mpa=300.0,
                             thickness_mm=200.0),
        IITPavePavementLayer(name="Subgrade", material="Subgrade",
                             modulus_mpa=50.0, thickness_mm=None),
    ))


def _mech_result(*,
                 eps_t_microstrain: float,
                 eps_v_microstrain: float,
                 is_placeholder: bool,
                 source: str = "external_exe") -> MechanisticResult:
    """Synthesize a result with two PointResults — fatigue + rutting probes."""
    bt_point = IITPavePointResult(
        z_mm=120.0, r_mm=0.0,
        sigma_z_mpa=0.5, sigma_r_mpa=0.1, sigma_t_mpa=0.1,
        epsilon_z_microstrain=-eps_t_microstrain,         # compressive vertical
        epsilon_r_microstrain=eps_t_microstrain,          # tensile horizontal
        epsilon_t_microstrain=eps_t_microstrain,          # tensile tangential
    )
    sg_point = IITPavePointResult(
        z_mm=320.0, r_mm=0.0,
        sigma_z_mpa=0.05, sigma_r_mpa=0.01, sigma_t_mpa=0.01,
        epsilon_z_microstrain=eps_v_microstrain,
        epsilon_r_microstrain=-eps_v_microstrain * 0.3,
        epsilon_t_microstrain=-eps_v_microstrain * 0.3,
    )
    return MechanisticResult(
        point_results=(bt_point, sg_point),
        references=(CodeRef("IRC:37-2018", "cl. 6.2",
                            "Multi-layered elastic analysis"),),
        is_placeholder=is_placeholder,
        source=source,
        notes="" if not is_placeholder else "synthetic placeholder fixture",
    )


_LABELS = (LABEL_FATIGUE, LABEL_RUTTING)


def main() -> int:
    print("=== 1) Refusal gate on placeholder mechanistic input ===")
    placeholder_in = MechanisticValidationInput(
        mech_result=_mech_result(eps_t_microstrain=150.0,
                                 eps_v_microstrain=300.0,
                                 is_placeholder=True, source="stub"),
        structure=_structure(),
        design_msa=30.0,
        point_labels=_LABELS,
    )
    s = compute_mechanistic_validation(placeholder_in)
    assert s.refused is True, s.refused
    assert s.is_placeholder is True
    assert s.fatigue.verdict is None and s.rutting.verdict is None
    assert s.fatigue.cumulative_life_msa is None
    assert s.rutting.cumulative_life_msa is None
    assert s.fatigue.refused is True and s.rutting.refused is True
    assert s.fatigue.refused_reason == REFUSED_PLACEHOLDER_MECH
    assert s.rutting.refused_reason == REFUSED_PLACEHOLDER_MECH
    assert "placeholder" in s.refused_reason.lower()
    assert MECH_VALIDATION_PLACEHOLDER_NOTE in s.notes
    print("  [PASS] refused=True; both verdicts None; reason cites placeholder")

    print("\n=== 2) Non-placeholder mocked result yields verdicts ===")
    real_in = MechanisticValidationInput(
        mech_result=_mech_result(eps_t_microstrain=150.0,
                                 eps_v_microstrain=300.0,
                                 is_placeholder=False, source="external_exe"),
        structure=_structure(),
        design_msa=30.0,
        point_labels=_LABELS,
    )
    s2 = compute_mechanistic_validation(real_in)
    assert s2.refused is False
    assert s2.fatigue.verdict in ("PASS", "FAIL")
    assert s2.rutting.verdict in ("PASS", "FAIL")
    assert s2.fatigue.cumulative_life_msa is not None
    assert s2.rutting.cumulative_life_msa is not None
    # is_placeholder still True because the *calibration* is placeholder.
    assert s2.is_placeholder is True
    assert s2.fatigue.calibration.label == "IRC37_PLACEHOLDER_80pct"
    assert s2.rutting.calibration.label == "IRC37_PLACEHOLDER_80pct"
    print(f"  [PASS] fatigue={s2.fatigue.verdict} N_f_msa="
          f"{s2.fatigue.cumulative_life_msa:.2f}; "
          f"rutting={s2.rutting.verdict} N_r_msa="
          f"{s2.rutting.cumulative_life_msa:.2f}")

    print("\n=== 3) PASS path: small strains + low MSA ===")
    pass_in = MechanisticValidationInput(
        mech_result=_mech_result(eps_t_microstrain=100.0,
                                 eps_v_microstrain=200.0,
                                 is_placeholder=False),
        structure=_structure(),
        design_msa=1.0,
        point_labels=_LABELS,
    )
    sp = compute_mechanistic_validation(pass_in)
    assert sp.fatigue.verdict == "PASS", sp.fatigue.cumulative_life_msa
    assert sp.rutting.verdict == "PASS", sp.rutting.cumulative_life_msa
    print(f"  [PASS] both PASS at design_msa=1.0")

    print("\n=== 4) FAIL path: large strains + high MSA ===")
    fail_in = MechanisticValidationInput(
        mech_result=_mech_result(eps_t_microstrain=400.0,
                                 eps_v_microstrain=900.0,
                                 is_placeholder=False),
        structure=_structure(),
        design_msa=100.0,
        point_labels=_LABELS,
    )
    sf = compute_mechanistic_validation(fail_in)
    assert sf.fatigue.verdict == "FAIL", sf.fatigue.cumulative_life_msa
    assert sf.rutting.verdict == "FAIL", sf.rutting.cumulative_life_msa
    print(f"  [PASS] both FAIL at design_msa=100.0")

    print("\n=== 5) Calibration swap retunes fatigue ===")
    base = get_fatigue_calibration()
    hot = FatigueCalibration(
        label="smoke-test-doubled-k1",
        k1=base.k1 * 2.0,
        k2=base.k2,
        k3=base.k3,
        reliability_pct=base.reliability_pct,
        is_placeholder=True,
    )
    set_fatigue_calibration(hot)
    s5 = compute_mechanistic_validation(real_in)
    assert s5.fatigue.cumulative_life_msa is not None
    assert s5.fatigue.cumulative_life_msa > s2.fatigue.cumulative_life_msa
    reset_fatigue_calibration()
    s5b = compute_mechanistic_validation(real_in)
    assert abs(s5b.fatigue.cumulative_life_msa
               - s2.fatigue.cumulative_life_msa) < 1e-9
    print(f"  [PASS] doubled k1 -> life {s2.fatigue.cumulative_life_msa:.2f} "
          f"-> {s5.fatigue.cumulative_life_msa:.2f}; reset honoured")

    print("\n=== 6) Per-call calibration override ===")
    override = compute_mechanistic_validation(
        MechanisticValidationInput(
            mech_result=real_in.mech_result,
            structure=real_in.structure,
            design_msa=real_in.design_msa,
            point_labels=_LABELS,
            fatigue_calibration=hot,
        )
    )
    assert (override.fatigue.cumulative_life_msa
            > s2.fatigue.cumulative_life_msa)
    # Module-level calibration was reset above and must remain unchanged.
    assert get_fatigue_calibration() is DEFAULT_FATIGUE_CALIBRATION
    print("  [PASS] per-call override honoured without mutating module state")

    print("\n=== 7) Strain-extraction fallback emits warning ===")
    s7 = compute_mechanistic_validation(MechanisticValidationInput(
        mech_result=real_in.mech_result,
        structure=real_in.structure,
        design_msa=30.0,
        point_labels=None,                           # forces fallback
    ))
    assert s7.fatigue.notes, "fatigue.notes must carry fallback warning"
    assert s7.rutting.notes, "rutting.notes must carry fallback warning"
    assert "falling back" in s7.fatigue.notes.lower()
    assert "falling back" in s7.rutting.notes.lower()
    assert "fallback" in (s7.notes or "").lower()
    # And not silently a verdict-OK case: we still got verdicts, but
    # provenance is traceable through the notes field.
    assert s7.fatigue.verdict in ("PASS", "FAIL")
    assert s7.rutting.verdict in ("PASS", "FAIL")
    print("  [PASS] fallback used + warning propagated end-to-end")

    print("\n=== 8) Fatigue refused when no bituminous modulus ===")
    s8 = compute_mechanistic_validation(MechanisticValidationInput(
        mech_result=real_in.mech_result,
        structure=_structure_no_bt(),
        design_msa=30.0,
        point_labels=_LABELS,
    ))
    assert s8.refused is True
    assert s8.fatigue.refused is True
    assert s8.fatigue.refused_reason == REFUSED_MISSING_E_BC
    assert s8.fatigue.verdict is None
    # Rutting path is independent of E_BC and should still verdict.
    assert s8.rutting.verdict in ("PASS", "FAIL")
    print("  [PASS] fatigue refused while rutting still verdicts")

    print("\n=== 9) References are IRC:37 CodeRefs ===")
    for check in (s2.fatigue, s2.rutting):
        assert check.references, f"empty references on {check}"
        for ref in check.references:
            assert isinstance(ref, CodeRef)
            assert ref.code_id == "IRC:37-2018", ref.code_id
    assert any(r.code_id == "IRC:37-2018" for r in s2.references)
    print("  [PASS] IRC:37-2018 references on fatigue + rutting + summary")

    print("\nPHASE 14 MECHANISTIC-VALIDATION SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
