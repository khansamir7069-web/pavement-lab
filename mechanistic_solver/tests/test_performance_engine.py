"""Unit tests for the performance profiling, caching, parallel processing, and batch solving engines."""
from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
from pathlib import Path
import pytest

from mechanistic_solver.core.models import Layer, ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.core.cache import global_cache
from mechanistic_solver.core.profiler import global_profiler
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.outputs.response import Response
from mechanistic_solver.optimization.parallel import execute_parallel
from mechanistic_solver.optimization.batch_solver import BatchSolverEngine


def test_cache_correctness_and_invalidation() -> None:
    """Verify cache gets, sets, statistics, and invalidation behave correctly."""
    global_cache.invalidate()
    stats = global_cache.get_statistics()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    
    # Check a missing key to trigger a miss
    assert global_cache.get("test_category", "key_missing") is None
    
    # Put a test key
    global_cache.set("test_category", "key1", "value1")
    assert global_cache.get("test_category", "key1") == "value1"
    
    stats_updated = global_cache.get_statistics()
    assert stats_updated["hits"] == 1
    assert stats_updated["misses"] == 1
    
    # Invalidate
    global_cache.invalidate("test_category")
    assert global_cache.get("test_category", "key1") is None


def test_sequential_vs_parallel_equality() -> None:
    """Verify executing items sequentially yields identical results to parallel execution."""
    items = list(range(10))
    def square(x: int) -> int:
        return x * x
        
    res_seq = execute_parallel(square, items, num_workers=1)
    res_par = execute_parallel(square, items, num_workers=2)
    
    assert res_seq == res_par
    assert res_seq == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]


def test_cancellation_handling() -> None:
    """Verify parallel executor exits cleanly when cancellation event is set."""
    items = list(range(100))
    def slow_square(x: int) -> int:
        return x * x
        
    ctx = multiprocessing.get_context("spawn")
    cancel_event = ctx.Event()
    cancel_event.set()  # Cancel immediately
    
    res = execute_parallel(slow_square, items, num_workers=2, cancellation_event=cancel_event)
    # Since cancellation is set, it should exit early and return None or incomplete results
    assert len(res) == 100
    assert all(r is None for r in res)


def test_batch_solver_correctness_and_isolation() -> None:
    """Verify batch solver processes multiple pavement jobs and isolates individual failures."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    points = [ObservationPoint(0.0, 0.0, 100.0)]
    
    batch_engine = BatchSolverEngine()
    
    jobs = [
        {"pavement": pavement, "loads": (load,), "points": points},
        {"pavement": pavement, "loads": (load,), "points": points},
        {"pavement": pavement, "loads": (), "points": points}  # Invalid job (empty loads)
    ]
    
    batch_res = batch_engine.solve_batch(jobs, num_workers=1)
    
    assert batch_res["total_jobs"] == 3
    assert batch_res["succeeded_jobs"] == 2
    assert batch_res["failed_jobs"] == 1
    
    # First two are successes, third is failure
    assert batch_res["results"][0]["status"] == "success"
    assert isinstance(batch_res["results"][0]["result"], Response)
    assert batch_res["results"][2]["status"] == "failed"
    assert "At least one wheel load configuration is required" in batch_res["results"][2]["error"]


def test_profiler_and_performance_report_generation() -> None:
    """Verify profiler measures phases and generates Markdown/JSON performance reports."""
    global_profiler.start()
    
    with global_profiler.measure("hankel_integration"):
        # simulate work
        pass
        
    global_profiler.batch_count = 5
    global_profiler.stop()
    
    cache_stats = global_cache.get_statistics()
    md_report = global_profiler.generate_markdown(cache_stats, num_workers=2)
    json_report = global_profiler.generate_json(cache_stats, num_workers=2)
    
    assert "# RoadX Computation Engine Performance Report" in md_report
    assert "Peak Memory Usage" in md_report
    assert "Cache Hit Ratio" in md_report
    
    json_data = json.loads(json_report)
    assert "runtimes" in json_data
    assert "memory" in json_data
    assert "cache" in json_data
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path, json_path = global_profiler.save_reports(cache_stats, num_workers=2, output_dir=tmp_dir)
        assert Path(md_path).exists()
        assert Path(json_path).exists()


def test_zero_engineering_output_differences() -> None:
    """Verify that cached solutions yield mathematically identical outputs to non-cached solutions."""
    l1 = Layer(name="Top", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35, density=2400.0)
    sub = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.4, density=1800.0)
    pavement = Pavement(layers=(l1,), subgrade=sub)
    load = WheelLoad(wheel_load=39.58, pressure=0.56, radius=150.0)
    points = [ObservationPoint(0.0, 0.0, 100.0)]
    
    solver = MechanisticSolver(mode="multilayer")
    
    # 1. Run with empty cache
    global_cache.invalidate()
    res_uncached = solver.solve(pavement, (load,), points)
    
    # 2. Run with filled cache
    res_cached = solver.solve(pavement, (load,), points)
    
    # 3. Assert identical output values
    assert res_uncached.surface_deflection == res_cached.surface_deflection
    assert len(res_uncached.stress_results) == len(res_cached.stress_results)
    
    for r1, r2 in zip(res_uncached.stress_results, res_cached.stress_results):
        assert r1["sigma_z"] == r2["sigma_z"]
        assert r1["sigma_r"] == r2["sigma_r"]
        assert r1["sigma_theta"] == r2["sigma_theta"]
        assert r1["tau_rz"] == r2["tau_rz"]
