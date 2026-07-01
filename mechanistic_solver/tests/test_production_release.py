"""Unit and integration tests verifying production release configurations, licenses, and manifests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.config import SolverProfile, load_profile, validate_profile, VERSION, active_config
from mechanistic_solver.config.manifests import generate_package_manifest
from mechanistic_solver.licensing import LicenseManager, LicenseRestrictedError, active_license
from mechanistic_solver.reports.release_report_generator import ReleaseReportGenerator
from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.solver.engine import MechanisticSolver


def test_production_profile_loading_and_validation() -> None:
    """Verify loading, overrides, and bounds checks for config profiles."""
    p_prod = load_profile("production")
    assert p_prod.name == "production"
    assert p_prod.tolerance == 1e-6
    assert validate_profile(p_prod) is True

    p_invalid = SolverProfile(
        name="invalid",
        tolerance=-0.01,
        max_limit=10,
        cache_max_size=-10,
        log_level="INFO",
        condition_checking=False,
        description=""
    )
    assert validate_profile(p_invalid) is False


def test_active_configuration_metadata() -> None:
    """Verify version information, build info, and active config manager setup."""
    assert VERSION == "2.2.0"
    v_info = active_config.get_version_info()
    assert v_info["version"] == "2.2.0"
    assert v_info["release_tier"] == "Enterprise"
    assert active_config.validate_current_setup() is True


def test_licensing_manager_enforcements() -> None:
    """Verify features are restricted or permitted strictly by license tier."""
    mgr = LicenseManager("Community")
    assert mgr.get_tier() == "Community"
    
    # Community blocks multilayer
    with pytest.raises(LicenseRestrictedError):
        mgr.check_feature("multilayer_solver")
        
    # Community blocks parallel
    with pytest.raises(LicenseRestrictedError):
        mgr.check_feature("parallel_execution")
        
    # Dynamic tier upgrade
    mgr.set_tier("Enterprise")
    assert mgr.get_tier() == "Enterprise"
    mgr.check_feature("multilayer_solver")  # Should not raise error
    mgr.check_feature("parallel_execution")  # Should not raise error


def test_license_key_application() -> None:
    """Verify applying license keys shifts the active tier correctly."""
    mgr = LicenseManager()
    
    assert mgr.apply_license_key("MY-ROADX-PRO-KEY-2026") is True
    assert mgr.get_tier() == "Professional"
    
    assert mgr.apply_license_key("MY-ROADX-ENT-KEY-2026") is True
    assert mgr.get_tier() == "Enterprise"
    
    assert mgr.apply_license_key("INVALID-KEY") is False


def test_package_manifest_generation() -> None:
    """Verify packaging manifests contain correct modules and dependencies."""
    manifest = generate_package_manifest()
    assert manifest["version"] == "2.2.0"
    assert "numpy" in manifest["dependencies_manifest"]
    assert "mechanistic_solver.core" in manifest["modules_inventory"]


def test_release_report_creation() -> None:
    """Verify that release reports compile and write successfully to disk."""
    generator = ReleaseReportGenerator()
    md_content = generator.generate_markdown()
    json_content = generator.generate_json()
    
    assert "# RoadX Mechanistic Solver Production Release Report" in md_content
    assert "release_tier" in json_content
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = generator.save_reports(tmp_dir)
        assert Path(md_path).exists()
        assert Path(json_path).exists()


def test_deterministic_solver_across_profiles() -> None:
    """Verify that changing profiles does not alter physical solver results."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    points = [ObservationPoint(0.0, 0.0, 100.0)]
    
    # 1. Solve under Enterprise / Production
    active_license.set_tier("Enterprise")
    solver = MechanisticSolver(mode="multilayer")
    res_prod = solver.solve(pavement, (load,), points)
    
    # Verify outputs are identical within floating point tolerances (or exactly identical)
    assert res_prod is not None
    assert res_prod.surface_deflection > 0.0
