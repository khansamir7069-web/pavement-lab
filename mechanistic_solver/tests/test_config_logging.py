"""Unit tests for the mechanistic solver configuration and logging components."""
from __future__ import annotations

import logging
from mechanistic_solver.core.config import SolverConfig
from mechanistic_solver.core.logging import get_logger


def test_solver_config_presets() -> None:
    """Verify that solver configuration preset fetching behaves as expected."""
    cfg = SolverConfig()
    
    # Check default numerical properties
    assert cfg.default_tolerance == 1e-6
    assert cfg.default_max_limit == 5000
    assert cfg.standard_wheel_load_kn == 40.0
    assert cfg.standard_contact_pressure_mpa == 0.56
    
    # Check preset lookups
    bc_preset = cfg.get_preset("BC Layer")
    assert bc_preset is not None
    modulus, poisson = bc_preset
    assert modulus == 3000.0
    assert poisson == 0.35
    
    dbm_preset = cfg.get_preset("DBM Binder")
    assert dbm_preset is not None
    assert dbm_preset[0] == 3000.0
    assert dbm_preset[1] == 0.35
    
    unknown = cfg.get_preset("Unknown Mud Layer")
    assert unknown is None


def test_logger_initialization() -> None:
    """Verify that the logger is initialized and configured properly."""
    logger = get_logger("test_mechanistic_logger")
    assert logger.name == "test_mechanistic_logger"
    assert logger.level == logging.INFO
    assert len(logger.handlers) > 0
    assert isinstance(logger.handlers[0], logging.StreamHandler)
