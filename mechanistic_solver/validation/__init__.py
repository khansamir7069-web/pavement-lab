"""Validation and parity routines comparing RoadX outputs against benchmark files."""
from __future__ import annotations

from mechanistic_solver.validation.iitpave_parser import IITPAVEOutputParser, ParsedIITPAVEOutput
from mechanistic_solver.validation.parity_models import ParityCase, ParityResult, ParityMetric, ParitySummary
from mechanistic_solver.validation.parity_metrics import (
    absolute_error,
    relative_error,
    percent_error,
    rmse,
    mae,
    max_abs_error,
    within_tolerance,
)
from mechanistic_solver.validation.parity_runner import ParityRunner
from mechanistic_solver.validation.parity_report import ParityReportGenerator

from mechanistic_solver.validation.benchmark_database import BenchmarkDatabase, BenchmarkCase
from mechanistic_solver.validation.benchmark_runner import BenchmarkRunner
from mechanistic_solver.validation.benchmark_statistics import BenchmarkStatistics
from mechanistic_solver.validation.calibration_report import CalibrationReportGenerator
