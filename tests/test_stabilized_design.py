import pytest

from app.core.stabilized_design import (
    StabilizedInput,
    compute_stabilized_design,
)


def test_stabilized_input_validation() -> None:
    # 1. Valid construction
    inp = StabilizedInput(
        ctb_thickness_mm=100.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C1.5/2.0",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        gsb_thickness_mm=150.0,
        bituminous_thickness_mm=100.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
    )
    assert inp.ctb_thickness_mm == 100.0
    assert inp.ctb_modulus_mpa == 5000.0
    assert inp.ctb_ucs_mpa == 4.5

    # 2. Physically invalid thicknesses (<= 0)
    with pytest.raises(ValueError, match="CTB thickness must be > 0"):
        StabilizedInput(ctb_thickness_mm=0.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=4.5)
    with pytest.raises(ValueError, match="CTB thickness must be > 0"):
        StabilizedInput(ctb_thickness_mm=-10.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=4.5)
    with pytest.raises(ValueError, match="CTS thickness must be > 0"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=4.5, cts_thickness_mm=0.0)

    # 3. Physically invalid moduli (<= 0)
    with pytest.raises(ValueError, match="CTB modulus must be > 0"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=0.0, ctb_ucs_mpa=4.5)
    with pytest.raises(ValueError, match="CTB modulus must be > 0"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=-500.0, ctb_ucs_mpa=4.5)

    # 4. Physically invalid Poisson's ratios (<= 0 or >= 0.5)
    with pytest.raises(ValueError, match="CTB Poisson's ratio must be between 0 and 0.5"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=4.5, ctb_poisson=0.0)
    with pytest.raises(ValueError, match="CTB Poisson's ratio must be between 0 and 0.5"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=4.5, ctb_poisson=0.5)

    # 5. Negative UCS
    with pytest.raises(ValueError, match="CTB UCS cannot be negative"):
        StabilizedInput(ctb_thickness_mm=100.0, ctb_modulus_mpa=5000.0, ctb_ucs_mpa=-1.0)


def test_ctb_valid_input_case() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.5,
        ctb_poisson=0.25,
        cts_class="C3/4",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
        gsb_thickness_mm=150.0,
        bituminous_thickness_mm=100.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
    )
    result = compute_stabilized_design(inp)
    
    # Verify warnings do not contain input value errors
    has_ucs_warn = any("Missing UCS" in w for w in result.warnings)
    has_mod_warn = any("Unrealistic" in w for w in result.warnings)
    has_poisson_warn = any("Poisson" in w for w in result.warnings)
    has_thick_warn = any("Very low" in w for w in result.warnings)

    assert not has_ucs_warn
    assert not has_mod_warn
    assert not has_poisson_warn
    assert not has_thick_warn

    # Preliminary notice must still be present
    assert any("CTB Fatigue Check (Preliminary)" in w for w in result.warnings)
    assert any("Engineer review required" in w for w in result.warnings)
    assert result.validation_mode == "Decision Support Mode"


def test_ctb_missing_ucs_warning() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=0.0, # UCS missing
        ctb_poisson=0.25,
        cts_class="C3/4",
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        cts_poisson=0.25,
    )
    result = compute_stabilized_design(inp)
    assert any("Missing UCS" in w for w in result.warnings)


def test_cts_valid_input_case() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        cts_class="C1.5/2.0",
        cts_thickness_mm=150.0,
        cts_modulus_mpa=3000.0,
    )
    result = compute_stabilized_design(inp)
    # Check that composition contains the CTS layer with correct properties
    cts_layer = next((l for l in result.stabilized_composition if l.material == "CTS"), None)
    assert cts_layer is not None
    assert cts_layer.thickness_mm == 150.0
    assert cts_layer.modulus_mpa == 3000.0


def test_unrealistic_modulus_warning() -> None:
    # Out of bounds modulus for CTB (< 3000)
    inp_ctb_low = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=2500.0,
        ctb_ucs_mpa=4.0,
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
    )
    result = compute_stabilized_design(inp_ctb_low)
    assert any("Unrealistic CTB modulus" in w for w in result.warnings)

    # Out of bounds modulus for CTS (> 6000)
    inp_cts_high = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        cts_thickness_mm=100.0,
        cts_modulus_mpa=7000.0,
    )
    result = compute_stabilized_design(inp_cts_high)
    assert any("Unrealistic CTS modulus" in w for w in result.warnings)


def test_invalid_poisson_ratio_warning() -> None:
    # Non-standard CTB Poisson's ratio (< 0.15)
    inp_ctb = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        ctb_poisson=0.10,
    )
    result = compute_stabilized_design(inp_ctb)
    assert any("Non-standard CTB Poisson's ratio" in w for w in result.warnings)


def test_low_thickness_warning() -> None:
    # Low CTB thickness (< 100 mm)
    inp_ctb = StabilizedInput(
        ctb_thickness_mm=80.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        cts_thickness_mm=150.0,
    )
    result = compute_stabilized_design(inp_ctb)
    assert any("Very low CTB thickness" in w for w in result.warnings)

    # Low CTS thickness (< 100 mm)
    inp_cts = StabilizedInput(
        ctb_thickness_mm=120.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        cts_thickness_mm=80.0,
    )
    result = compute_stabilized_design(inp_cts)
    assert any("Very low CTS thickness" in w for w in result.warnings)


def test_flexible_vs_stabilized_comparison_regression() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=100.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
        cts_thickness_mm=100.0,
        cts_modulus_mpa=3000.0,
        gsb_thickness_mm=150.0,
        bituminous_thickness_mm=100.0,
        flexible_design_msa=10.0,
        flexible_subgrade_cbr=5.0,
    )
    result = compute_stabilized_design(inp)
    
    total_stab = 100.0 + 100.0 + 100.0 + 150.0 # bit + ctb + cts + gsb = 450 mm
    assert sum(l.thickness_mm for l in result.stabilized_composition) == total_stab

    total_flex = sum(l.thickness_mm for l in result.conventional_composition)
    expected_savings = total_flex - total_stab
    expected_pct = (expected_savings / total_flex * 100.0) if total_flex > 0 else 0.0

    assert result.thickness_savings_mm == expected_savings
    assert abs(result.thickness_savings_pct - expected_pct) < 0.01
    assert result.comparison_label == "Indicative comparison against conventional flexible pavement"


def test_validation_mode_toggling() -> None:
    inp = StabilizedInput(
        ctb_thickness_mm=100.0,
        ctb_modulus_mpa=5000.0,
        ctb_ucs_mpa=4.0,
    )
    
    # Decision support mode
    res_dec = compute_stabilized_design(inp, has_mechanistic_validation=False)
    assert res_dec.validation_mode == "Decision Support Mode"

    # Mechanistic verified mode
    res_mech = compute_stabilized_design(inp, has_mechanistic_validation=True)
    assert res_mech.validation_mode == "Mechanistic Verified Mode"
