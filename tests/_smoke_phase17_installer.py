"""Phase-17 installer smoke.

Pure-Python, no Qt, no DB, no real PyInstaller invocation. Verifies the
packaging contract: every resource the frozen bundle ships must remain
locatable from the source tree via the same lookup logic, the
``_resource_root`` switch honours ``sys._MEIPASS`` correctly, and the
``ExternalExeRunner`` enforces its placeholder-safety contract.

Coverage:

  1. _resource_root() returns the source tree when not frozen.
  2. _resource_root() returns sys._MEIPASS when set (frozen mode
     simulation).
  3. Sample-project corpus loads from the bundled path (5 samples
     under app/data/sample_projects/).
  4. CodeRef registry + mix specs load from app/data/.
  5. Report templates directory exists (shipped by the spec).
  6. External binary directory exists (operator drop-in target).
  7. ExternalExeRunner raises FileNotFoundError with bundle_iitpave.md
     reference when the binary is absent — placeholder safety.
  8. StubRunner end-to-end through parser still produces
     MechanisticResult(is_placeholder=True, source="stub").
  9. PyInstaller spec at build/installer/pyinstaller.spec is
     syntactically valid Python (compile-only check; we don't try to
     execute PyInstaller's injected globals).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import app.config as cfg
from app.core import (
    IITPaveLoadConfig,
    IITPavePavementLayer,
    PavementStructure,
    build_iitpave_input,
    default_evaluation_points,
    parse_iitpave_output,
)
from app.core.code_refs import CODE_REGISTRY
from app.core.compliance import MIX_SPECS
from app.core.iitpave import (
    ExternalExeRunner,
    StubRunner,
    default_iitpave_exe_path,
)
from app.data.sample_projects import list_samples, load_sample, sample_dir


def _structure() -> PavementStructure:
    return PavementStructure(layers=(
        IITPavePavementLayer(name="BC",  material="BC",  modulus_mpa=3000.0,
                             thickness_mm=40.0),
        IITPavePavementLayer(name="DBM", material="DBM", modulus_mpa=2500.0,
                             thickness_mm=80.0),
        IITPavePavementLayer(name="Subgrade", material="Subgrade",
                             modulus_mpa=50.0, thickness_mm=None),
    ))


def main() -> int:
    print("=== 1) _resource_root() in source mode ===")
    root_source = cfg._resource_root()
    assert root_source.is_dir(), root_source
    # In source mode it's the app/ directory.
    assert (root_source / "config.py").is_file(), root_source
    print(f"  [PASS] APP_DIR={root_source}")

    print("\n=== 2) _resource_root() honours sys._MEIPASS (frozen sim) ===")
    fake_bundle = Path(tempfile.mkdtemp(prefix="meipass_"))
    prev_mei = getattr(sys, "_MEIPASS", None)
    try:
        sys._MEIPASS = str(fake_bundle)
        frozen_root = cfg._resource_root()
        assert Path(frozen_root) == fake_bundle, (frozen_root, fake_bundle)
        print(f"  [PASS] _MEIPASS={fake_bundle} -> resource_root resolved to bundle")
    finally:
        if prev_mei is None:
            del sys._MEIPASS  # type: ignore[attr-defined]
        else:
            sys._MEIPASS = prev_mei

    print("\n=== 3) Sample-project corpus loads from bundled path ===")
    samples = list_samples()
    assert len(samples) >= 5, samples
    sd = sample_dir()
    assert sd.is_dir(), sd
    for name in samples:
        blob = load_sample(name)
        assert blob["name"] == name
        # Engineering intent fields must be present.
        for key in ("condition", "traffic", "structural", "mechanistic",
                    "calibration_overrides", "expected"):
            assert key in blob, f"{name} missing {key!r}"
    print(f"  [PASS] {len(samples)} sample(s) located under {sd.name}/")

    print("\n=== 4) Code registry + mix specs load from app/data ===")
    assert len(CODE_REGISTRY) > 0, "CodeRef registry empty"
    assert "IRC:37-2018" in CODE_REGISTRY
    assert len(MIX_SPECS) > 0, "MIX_SPECS empty"
    print(f"  [PASS] CODE_REGISTRY={len(CODE_REGISTRY)} entries; "
          f"MIX_SPECS={len(MIX_SPECS)} entries")

    print("\n=== 5) Report templates directory ships ===")
    assert cfg.TEMPLATES_DIR.is_dir(), cfg.TEMPLATES_DIR
    print(f"  [PASS] TEMPLATES_DIR={cfg.TEMPLATES_DIR}")

    print("\n=== 6) External binary directory ships (operator drop-in) ===")
    external = cfg.APP_DIR / "external" / "iitpave"
    assert external.is_dir(), external
    # Canonical default path is reported even when no binary exists.
    default_path = default_iitpave_exe_path()
    assert default_path.parent == external, (default_path, external)
    print(f"  [PASS] {external.relative_to(cfg.APP_DIR)} present; "
          f"default exe path={default_path.name}")

    print("\n=== 7) ExternalExeRunner refuses when binary absent ===")
    # Point at a path we know does not exist.
    missing = Path(tempfile.gettempdir()) / "definitely_not_iitpave.exe"
    if missing.exists():
        missing.unlink()
    runner = ExternalExeRunner(exe_path=missing)
    try:
        runner.run("# dummy input\n0\n")
        raise AssertionError("ExternalExeRunner.run() should have raised")
    except FileNotFoundError as e:
        msg = str(e)
        assert "bundle_iitpave.md" in msg, msg
        assert str(missing) in msg or "IITPAVE" in msg
        print(f"  [PASS] FileNotFoundError raised with bundle_iitpave.md hint")

    print("\n=== 8) StubRunner -> parser end-to-end is placeholder-safe ===")
    structure = _structure()
    load = IITPaveLoadConfig()
    points = default_evaluation_points(structure)
    text = build_iitpave_input(structure, load, points)
    out = StubRunner().run(text)
    result = parse_iitpave_output(out)
    assert result.is_placeholder is True
    assert result.source == "stub"
    assert len(result.point_results) == len(points)
    print(f"  [PASS] stub round-trip placeholder=True source={result.source!r}")

    print("\n=== 9) PyInstaller spec is syntactically valid Python ===")
    spec_path = Path(__file__).resolve().parents[1] / "build" / "installer" / "pyinstaller.spec"
    assert spec_path.is_file(), spec_path
    src = spec_path.read_text(encoding="utf-8")
    # Compile only — running would require PyInstaller's injected
    # SPECPATH / Analysis / PYZ / EXE / COLLECT globals.
    compile(src, str(spec_path), "exec")
    # Sanity content check: must reference the bundled data trees we
    # rely on at runtime.
    for must_have in (
        '"app/data"',
        '"app/external"',
        '"app/ui"',
        '"app/reports/templates"',
        "PIL",
    ):
        assert must_have in src, f"spec missing reference {must_have!r}"
    print(f"  [PASS] {spec_path.name} compiles + bundles required data trees")

    print("\nPHASE 17 INSTALLER SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
