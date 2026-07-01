"""Unit and integration tests verifying Phase 4 advanced pavement engineering components."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.advanced import (
    PronyTerm,
    ViscoelasticMaterial,
    BinderGrade,
    TemperaturePavementModel,
    DynamicWheelLoad,
    TyrePosition,
    AxleConfiguration,
    MovingLoadSimulator,
    AircraftMetadata,
    AirportGearFactory,
    OverlayDesign,
    CompositePavementModel,
    IndustrialLoadTemplate,
    IndustrialPavementModel,
    StochasticVariable,
    ReliabilityEngine,
    AdvancedReportGenerator
)
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_elastic_compatibility() -> None:
    """Verify that a viscoelastic material with no Prony terms matches its static modulus."""
    mat = ViscoelasticMaterial(e_inf=3000.0, prony_terms=[])
    assert mat.get_relaxation_modulus(0.1) == 3000.0
    assert mat.get_relaxation_modulus(10.0, temp=40.0) == 3000.0
    assert mat.get_dynamic_modulus(10.0) == 3000.0


def test_viscoelastic_math() -> None:
    """Verify relaxation modulus decay and temperature shift factors (WLF and Arrhenius)."""
    terms = [
        PronyTerm(modulus=1000.0, relaxation_time=0.1),
        PronyTerm(modulus=500.0, relaxation_time=1.0)
    ]
    mat = ViscoelasticMaterial(e_inf=1500.0, prony_terms=terms, t_ref=20.0)
    
    # Check relaxation modulus decay
    e_0 = mat.get_relaxation_modulus(0.0)
    e_1 = mat.get_relaxation_modulus(0.5)
    e_inf = mat.get_relaxation_modulus(100.0)
    
    assert e_0 == 3000.0
    assert e_1 < e_0
    assert e_inf >= 1500.0
    
    # Check shift factors
    a_t_wlf = mat.get_shift_factor(40.0, method="wlf")
    a_t_arr = mat.get_shift_factor(40.0, method="arrhenius")
    assert a_t_wlf < 1.0  # Warmer temp reduces reduced time
    assert a_t_arr < 1.0


def test_temperature_corrections() -> None:
    """Verify depth temperature profiles, corrected modulus, and thermal strain."""
    # FHWA depth profile
    temp_depth = TemperaturePavementModel.get_temperature_at_depth(
        surface_temp_celsius=40.0, mean_air_temp_celsius=25.0, depth_mm=100.0
    )
    assert 25.0 < temp_depth < 40.0
    
    # Corrected modulus
    e_corr = TemperaturePavementModel.get_corrected_modulus(
        base_modulus_mpa=3000.0, temperature_celsius=40.0, reference_temp_celsius=20.0
    )
    assert e_corr < 3000.0  # warmer -> softer
    
    # Thermal strain
    eps_th = TemperaturePavementModel.get_thermal_strain(
        expansion_coeff=1.5e-5, temp_initial=20.0, temp_final=40.0
    )
    assert eps_th == pytest.approx(3e-4)

    # Seasonal correction factor
    assert TemperaturePavementModel.get_seasonal_modulus_factor("winter") == 1.8
    assert TemperaturePavementModel.get_seasonal_modulus_factor("summer") == 0.6


def test_dynamic_loading() -> None:
    """Verify harmonic and impulse load generation and speed conversions."""
    load = DynamicWheelLoad(base_load_kn=40.0, tyre_pressure_mpa=0.56, contact_radius_mm=150.0, speed_kmh=60.0)
    
    assert load.get_angular_frequency() == pytest.approx(20.0 * 3.14159265, abs=1e-2)
    
    duration = load.get_loading_time_duration()
    assert duration > 0.0
    
    eq_freq = load.get_equivalent_frequency()
    assert eq_freq > 0.0
    
    # Load history values
    val_harmonic = load.get_harmonic_load_at_time(0.05)
    val_impulse = load.get_impulse_load_at_time(0.01)
    
    assert -40.0 <= val_harmonic <= 40.0
    assert 0.0 <= val_impulse <= 40.0


def test_moving_wheel_responses_and_envelope() -> None:
    """Verify dual tyre coordinate mapping and critical response envelope extraction."""
    tyres = AxleConfiguration.dual_tyre(wheel_load_kn=40.0, spacing_mm=330.0)
    assert len(tyres) == 2
    assert tyres[0].wheel_load_kn == 20.0
    
    sim = MovingLoadSimulator(tyres, velocity_kmh=60.0)
    
    # Simulate a small run
    solver = MechanisticSolver(mode="multilayer")
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    
    steps = [-0.01, 0.0, 0.01]  # Seconds around observation point
    envelope = sim.compute_critical_envelope(
        solver=solver,
        pavement=pavement,
        obs_x=0.0,
        obs_y=0.0,
        obs_z=100.0,
        time_steps=steps
    )
    
    assert envelope["max_displacement_mm"] > 0.0
    assert envelope["max_tensile_strain_microstrain"] > 0.0
    assert envelope["max_compressive_strain_microstrain"] < 0.0
    assert len(envelope["time_history"]["deflection"]) == 3


def test_airport_pavement_gear_and_metadata() -> None:
    """Verify aircraft metadata and Boeing 777 tridem-dual gear layout generation."""
    # Metadata check
    ac_key = "B777-300ER"
    meta = AirportGearFactory.get_gear_tyres(ac_key)
    assert len(meta) == 6
    assert all(t.wheel_load_kn == pytest.approx(270.0) for t in meta)


def test_composite_pavement_design() -> None:
    """Verify overlay design recommendations and Westergaard rigid base bending stress."""
    design = OverlayDesign(existing_slab_thickness_mm=250.0, existing_elastic_modulus_mpa=30000.0, design_traffic_msa=10.0, deflection_rebound_mm=1.5)
    t_ol = CompositePavementModel.get_overlay_thickness_recommendation(design)
    assert t_ol > 40.0
    
    # Westergaard concrete stress
    stress = CompositePavementModel.get_rigid_slab_bending_stress(
        wheel_load_kn=40.0, slab_thickness_mm=250.0, slab_modulus_mpa=30000.0, subgrade_reaction_k_mpa_m=48.0
    )
    assert stress > 0.0
    
    # Slip parameter
    slip = CompositePavementModel.get_interface_slip_factor(shear_stress_mpa=0.5, slip_parameter_alpha=0.1)
    assert slip == pytest.approx(0.05)


def test_industrial_pavement_reps() -> None:
    """Verify reach stacker load templates and industrial fatigue/point load models."""
    rs = IndustrialPavementModel.get_container_yard_fatigue_life(tensile_strain=2e-4)
    assert rs > 0.0
    
    p_allow = IndustrialPavementModel.get_warehouse_slab_allowable_load(slab_thickness_mm=200.0)
    assert p_allow > 0.0


def test_probabilistic_reliability_analysis() -> None:
    """Verify Monte Carlo parameter sampling, reliability %, and sensitivity rankings."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    
    traffic_stoch = StochasticVariable(mean=10.0, std_dev=2.0)
    
    engine = ReliabilityEngine()
    res = engine.run_monte_carlo(
        pavement=pavement,
        loads=(load,),
        traffic_msa=traffic_stoch,
        modulus_stds=[300.0, 5.0],
        thickness_stds=[10.0],
        num_simulations=10
    )
    
    assert res["total_simulations"] == 10
    assert 0.0 <= res["reliability_pct"] <= 100.0
    assert isinstance(res["reliability_index_beta"], float)
    assert len(res["sensitivity_ranking"]) > 0


def test_advanced_report_generation() -> None:
    """Verify advanced evaluation reports save successfully in Markdown and JSON formats."""
    results = {
        "viscoelastic": {"t_ref": 20.0, "e_t_0_1s": 2500.0, "e_star_10hz": 2800.0},
        "temperature": {"surface_temp_celsius": 40.0, "modulus_correction_factor": 0.85, "thermal_strain": 1.5e-4},
        "moving_load": {"max_displacement_mm": 0.35, "max_tensile_strain_microstrain": 120.0, "max_compressive_strain_microstrain": -85.0},
        "composite": {"overlay_recommendation_mm": 75.0, "rigid_slab_bending_stress_mpa": 1.25},
        "reliability": {
            "total_simulations": 100,
            "reliability_pct": 95.0,
            "reliability_index_beta": 1.645,
            "failure_probability": 0.05,
            "sensitivity_ranking": [{"parameter": "bc_thickness", "correlation_coefficient": -0.85}]
        }
    }
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = AdvancedReportGenerator.save_reports(results, tmp_dir)
        assert Path(md_path).exists()
        assert Path(json_path).exists()
        
        md_content = Path(md_path).read_text(encoding="utf-8")
        assert "# RoadX Advanced Pavement Engineering Report" in md_content
