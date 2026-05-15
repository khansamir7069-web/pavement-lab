"""Phase-13 IITPAVE integration-layer smoke.

Pure-Python, no Qt, no DB, no filesystem. Exercises only the new
``app.core.iitpave`` package: structure dataclasses, input builder,
stub runner, output parser, adapter from Phase-4 layers, and the
declared-but-blocked external-exe runner.

Coverage:

  1. Structure validation (semi-infinite subgrade rule).
  2. Default evaluation points point at bottom-of-BT and top-of-subgrade.
  3. ``build_iitpave_input`` emits the expected line shape.
  4. ``StubRunner`` is deterministic (same input -> same output bytes).
  5. Parser round-trip yields a MechanisticResult with one PointResult
     per input EvaluationPoint, ``is_placeholder=True``,
     ``source="stub"`` and IRC:37 references.
  6. ``ExternalExeRunner.run`` raises NotImplementedError (loud failure).
  7. Adapter from Phase-4 structural layers appends the subgrade
     correctly and preserves layer order / modulus / thickness.
  8. Stress decays with depth and strain at top-of-subgrade is bounded
     (sanity ranges only — values are placeholder).
"""
from __future__ import annotations

from app.core import (
    IITPaveEvaluationPoint,
    IITPaveExternalExeRunner,
    IITPaveLoadConfig,
    IITPavePavementLayer,
    IITPaveStubRunner,
    MechanisticResult,
    PavementStructure,
    build_iitpave_input,
    default_evaluation_points,
    iitpave_from_structural_layers,
    is_known_stub_output,
    parse_iitpave_output,
)
from app.core.code_refs import CodeRef
from app.core.structural_design import PavementLayer as StructuralLayer


def _build_structure() -> PavementStructure:
    return PavementStructure(layers=(
        IITPavePavementLayer(name="BC",  material="BC",  modulus_mpa=3000.0,
                             poisson_ratio=0.35, thickness_mm=40.0),
        IITPavePavementLayer(name="DBM", material="DBM", modulus_mpa=2500.0,
                             poisson_ratio=0.35, thickness_mm=80.0),
        IITPavePavementLayer(name="GSB", material="GSB", modulus_mpa=300.0,
                             poisson_ratio=0.35, thickness_mm=200.0),
        IITPavePavementLayer(name="Subgrade", material="Subgrade",
                             modulus_mpa=50.0,  poisson_ratio=0.40,
                             thickness_mm=None),
    ))


def main() -> int:
    print("=== 1) Structure validation ===")
    s = _build_structure()
    assert s.total_finite_thickness_mm == 320.0
    assert s.bituminous_thickness_mm() == 120.0
    # Subgrade-rule violations are rejected.
    try:
        PavementStructure(layers=(
            IITPavePavementLayer(name="BC", material="BC", modulus_mpa=3000,
                                 thickness_mm=40),
        ))
        raise AssertionError("expected ValueError for missing semi-infinite subgrade")
    except ValueError:
        pass
    try:
        PavementStructure(layers=(
            IITPavePavementLayer(name="X", material="X", modulus_mpa=10.0,
                                 thickness_mm=None),
            IITPavePavementLayer(name="Y", material="Y", modulus_mpa=20.0,
                                 thickness_mm=None),
        ))
        raise AssertionError("expected ValueError for non-finite intermediate layer")
    except ValueError:
        pass
    print(f"  [PASS] total_finite_thickness=320, BT_thickness=120, rules enforced")

    print("\n=== 2) Default evaluation points ===")
    pts = default_evaluation_points(s)
    assert len(pts) == 2
    assert pts[0].z_mm == 120.0 and pts[0].label == "bottom_of_BT"
    assert pts[1].z_mm == 320.0 and pts[1].label == "top_of_subgrade"
    print("  [PASS]", [(p.z_mm, p.label) for p in pts])

    print("\n=== 3) build_iitpave_input shape ===")
    load = IITPaveLoadConfig()
    text = build_iitpave_input(s, load, pts)
    assert "pavement_lab iitpave input" in text
    # First non-comment data line is the layer count.
    data_lines = [ln for ln in text.splitlines()
                  if ln.strip() and not ln.strip().startswith("#")]
    assert data_lines[0] == "4"                           # 4 layers
    # 4 layer rows + 1 load row + 1 point-count row + 2 point rows = 8
    assert len(data_lines) == 1 + 4 + 1 + 1 + 2, data_lines
    # Subgrade line ends with h=0
    assert data_lines[4].endswith("0.0000")
    # Load row carries the 3 IRC:37 default tokens.
    load_tokens = data_lines[5].split()
    assert float(load_tokens[0]) == 20.0
    assert abs(float(load_tokens[1]) - 0.56) < 1e-9
    assert float(load_tokens[2]) == 310.0
    print("  [PASS] text shape OK")

    print("\n=== 4) StubRunner is deterministic ===")
    r = IITPaveStubRunner()
    o1 = r.run(text)
    o2 = r.run(text)
    assert o1 == o2
    assert is_known_stub_output(o1)
    print("  [PASS] same input -> same output")

    print("\n=== 5) Parser round-trip ===")
    result: MechanisticResult = parse_iitpave_output(o1)
    assert len(result.point_results) == 2
    assert result.is_placeholder is True
    assert result.source == "stub"
    # References are IRC:37 CodeRefs.
    assert any(isinstance(ref, CodeRef) and ref.code_id == "IRC:37-2018"
               for ref in result.references), result.references
    # Points come back in the same z-order we supplied.
    assert result.point_results[0].z_mm == 120.0
    assert result.point_results[1].z_mm == 320.0
    print(f"  [PASS] n_points={len(result.point_results)} source={result.source!r}")

    print("\n=== 6) ExternalExeRunner refuses to run in V1 ===")
    try:
        IITPaveExternalExeRunner().run(text)
        raise AssertionError("ExternalExeRunner.run must raise in V1")
    except NotImplementedError as e:
        assert "Phase 17" in str(e) or "not bundled" in str(e), str(e)
    print("  [PASS] NotImplementedError raised")

    print("\n=== 7) Adapter from structural layers ===")
    structural_comp = (
        StructuralLayer(name="BC",  thickness_mm=40,  material="BC",  modulus_mpa=3000),
        StructuralLayer(name="DBM", thickness_mm=80,  material="DBM", modulus_mpa=2500),
        StructuralLayer(name="GSB", thickness_mm=200, material="GSB", modulus_mpa=300),
    )
    s2 = iitpave_from_structural_layers(structural_comp, subgrade_mr_mpa=50.0)
    assert len(s2.layers) == 4
    assert s2.layers[-1].thickness_mm is None
    assert s2.layers[-1].modulus_mpa == 50.0
    assert s2.layers[0].material == "BC" and s2.layers[0].thickness_mm == 40
    # Modulus preserved
    assert s2.layers[1].modulus_mpa == 2500.0
    print("  [PASS] adapter appends subgrade correctly")

    print("\n=== 8) Sanity on stub sigma/epsilon values ===")
    # σ_z monotonically non-increasing with depth under the stub heuristic.
    bt = result.point_results[0]
    sg = result.point_results[1]
    assert bt.sigma_z_mpa > sg.sigma_z_mpa > 0.0, (bt.sigma_z_mpa, sg.sigma_z_mpa)
    # Compressive ε_z at top-of-subgrade is non-zero and finite.
    assert abs(sg.epsilon_z_microstrain) > 0.0
    assert abs(sg.epsilon_z_microstrain) < 1.0e6  # < 100% strain — sanity only
    print(f"  [PASS] bt.sigma_z={bt.sigma_z_mpa:.4f} > sg.sigma_z={sg.sigma_z_mpa:.4f}")

    print("\nPHASE 13 IITPAVE SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
