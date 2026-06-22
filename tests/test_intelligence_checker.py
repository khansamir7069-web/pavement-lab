"""Unit tests for Phase M: Engineering Intelligence Checker."""
from __future__ import annotations

import pytest
from app.core.structural_design import PavementLayer
from app.core.intelligence_checker import check_pavement_intelligence


def test_healthy_pavement_stack():
    """Verify that a standard, healthy conventional flexible pavement scores 100."""
    comp = (
        PavementLayer(name="Bituminous Concrete", thickness_mm=40.0, material="BC", modulus_mpa=3000.0, poisson=0.35),
        PavementLayer(name="Dense Bituminous Macadam", thickness_mm=80.0, material="DBM", modulus_mpa=3000.0, poisson=0.35),
        PavementLayer(name="Wet Mix Macadam", thickness_mm=250.0, material="WMM", modulus_mpa=450.0, poisson=0.35),
        PavementLayer(name="Granular Sub-base", thickness_mm=200.0, material="GSB", modulus_mpa=150.0, poisson=0.35),
    )
    res = check_pavement_intelligence(comp, subgrade_mr_mpa=50.0)
    assert res.health_score == 100.0
    assert res.risk_level == "Healthy"
    assert len(res.warnings) == 0


def test_bad_modular_ratio():
    """Verify that a granular base to sub-base modulus ratio > 4.0 is flagged."""
    comp = (
        PavementLayer(name="BC", thickness_mm=40.0, material="BC", modulus_mpa=3000.0),
        PavementLayer(name="WMM", thickness_mm=250.0, material="WMM", modulus_mpa=700.0), # Too stiff for sub-base
        PavementLayer(name="GSB", thickness_mm=200.0, material="GSB", modulus_mpa=100.0), # ratio = 7.0 > 4.0
    )
    res = check_pavement_intelligence(comp, subgrade_mr_mpa=50.0)
    assert res.health_score < 100.0
    assert any("Base-to-subbase modulus ratio" in w for w in res.warnings)


def test_stiffness_inversion_and_exemption():
    """Verify that stiffness inversion is flagged, but cover-over-CTB is exempted."""
    # Case A: cover-over-CTB (exempted)
    comp_exempt = (
        PavementLayer(name="BC Cover", thickness_mm=100.0, material="BC", modulus_mpa=3000.0),
        PavementLayer(name="CTB Base", thickness_mm=120.0, material="CTB", modulus_mpa=5000.0), # stiffer lower layer
    )
    res_exempt = check_pavement_intelligence(comp_exempt)
    # CTB fatigue warning and disclaimers are not modular ratio warnings. Health score should stay 100
    assert not any("Stiffness inversion" in w for w in res_exempt.warnings)

    # Case B: Inversion that is NOT cover-over-CTB (e.g. weak base over stiff sub-base)
    comp_inversion = (
        PavementLayer(name="WMM", thickness_mm=150.0, material="WMM", modulus_mpa=250.0),
        PavementLayer(name="GSB", thickness_mm=200.0, material="GSB", modulus_mpa=600.0), # lower is stiffer
    )
    res_inv = check_pavement_intelligence(comp_inversion)
    assert any("Stiffness inversion detected" in w for w in res_inv.warnings)


def test_stiff_ctb_over_weak_support():
    """Verify that placing extremely stiff CTB directly over weak granular sub-base or subgrade is flagged."""
    comp = (
        PavementLayer(name="BC Cover", thickness_mm=100.0, material="BC", modulus_mpa=3000.0),
        PavementLayer(name="CTB Base", thickness_mm=150.0, material="CTB", modulus_mpa=5000.0),
        PavementLayer(name="Weak Sub-base", thickness_mm=150.0, material="GSB", modulus_mpa=150.0), # modulus < 500 MPa
    )
    res = check_pavement_intelligence(comp)
    assert any("placed directly over weak support" in w for w in res.warnings)


def test_poisson_ratio_limits():
    """Verify that invalid and non-standard Poisson's ratios are correctly flagged."""
    # Invalid Poisson (> 0.49)
    with pytest.raises(ValueError, match="Poisson's ratio must be physically realistic"):
        PavementLayer(name="BC", thickness_mm=40.0, material="BC", modulus_mpa=3000.0, poisson=0.55)

    # Non-standard Poisson for stabilized (e.g. 0.40)
    comp_non_standard = (
        PavementLayer(name="CTB", thickness_mm=150.0, material="CTB", modulus_mpa=5000.0, poisson=0.40),
    )
    res = check_pavement_intelligence(comp_non_standard)
    assert any("Non-standard Poisson's ratio" in w for w in res.warnings)


def test_incorrect_thickness():
    """Verify that unusual layer thicknesses are flagged."""
    # BC too thick
    comp_thick = (
        PavementLayer(name="BC", thickness_mm=80.0, material="BC", modulus_mpa=3000.0),
    )
    res = check_pavement_intelligence(comp_thick)
    assert any("Unusual BC layer thickness" in w for w in res.warnings)

    # CTB too thin (< 100mm)
    comp_thin = (
        PavementLayer(name="CTB", thickness_mm=80.0, material="CTB", modulus_mpa=5000.0),
    )
    res = check_pavement_intelligence(comp_thin)
    assert any("below the minimum recommended structural lift" in w for w in res.warnings)


def test_material_placement_mismatch():
    """Verify that a lower-tier material placed above a higher-tier material triggers a warning."""
    comp = (
        PavementLayer(name="Granular Sub-base", thickness_mm=200.0, material="GSB", modulus_mpa=150.0), # Tier 1 (GSB)
        PavementLayer(name="BC Cover", thickness_mm=100.0, material="BC", modulus_mpa=3000.0), # Tier 5 (BC)
    )
    res = check_pavement_intelligence(comp)
    assert any("Material placement anomaly" in w for w in res.warnings)


def test_missing_data():
    """Verify that missing modulus is flagged."""
    comp = (
        PavementLayer(name="BC", thickness_mm=40.0, material="BC", modulus_mpa=None),
    )
    res = check_pavement_intelligence(comp)
    assert any("Missing modulus for layer" in w for w in res.warnings)
