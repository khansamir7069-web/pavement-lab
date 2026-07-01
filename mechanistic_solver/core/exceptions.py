"""Custom engineering exceptions for the mechanistic solver.

Ensures that numerical convergence, validation bounds, and unit conversions
throw semantic errors instead of generic Python exceptions.
"""
from __future__ import annotations


class EngineeringError(ValueError):
    """Base exception for all engineering and validation errors."""
    pass


class NegativeThicknessError(EngineeringError):
    """Raised when a finite pavement layer thickness is non-positive."""
    pass


class InvalidPoissonRatioError(EngineeringError):
    """Raised when Poisson's ratio violates elastic limits (0, 0.5]."""
    pass


class InvalidElasticModulusError(EngineeringError):
    """Raised when elastic modulus values are negative or out of realistic ranges."""
    pass


class InvalidLayerConfigurationError(EngineeringError):
    """Raised when layer stack orders or subgrade boundary conditions are invalid."""
    pass


class UnitConversionError(EngineeringError):
    """Raised when attempting incompatible unit conversions or parsing invalid units."""
    pass


class SolverConvergenceError(RuntimeError):
    """Raised when numerical integrations or boundary equations fail to converge."""
    pass
