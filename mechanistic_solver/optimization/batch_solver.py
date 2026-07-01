"""Batch solver engine for large-scale pavement computation sweeps."""
from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Sequence

from mechanistic_solver.core.models import ObservationPoint, Pavement, WheelLoad
from mechanistic_solver.outputs.response import Response
from mechanistic_solver.solver.engine import MechanisticSolver
from mechanistic_solver.design.irc37_engine import IRC37DesignEngine
from mechanistic_solver.optimization.parallel import execute_parallel


class BatchSolverEngine:
    """Orchestrator for running high-throughput, concurrent batch pavement analyses."""

    def __init__(self, solver: MechanisticSolver | None = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")
        self.design_engine = IRC37DesignEngine(solver=self.solver)

    def solve_batch(
        self,
        jobs: Sequence[Mapping[str, Any]],  # List of dict with {"pavement": Pavement, "loads": Sequence[WheelLoad], "points": Sequence[ObservationPoint]}
        num_workers: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancellation_event: Any = None
    ) -> Mapping[str, Any]:
        """Solve a batch of pavement analysis jobs concurrently with failure isolation."""
        start_time = time.perf_counter()
        
        def run_single_job(job: Mapping[str, Any]) -> dict[str, Any]:
            pavement = job["pavement"]
            loads = job["loads"]
            points = job["points"]
            try:
                res = self.solver.solve(pavement, loads, points)
                return {"status": "success", "result": res}
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        raw_results = execute_parallel(
            func=run_single_job,
            items=jobs,
            num_workers=num_workers,
            progress_callback=progress_callback,
            cancellation_event=cancellation_event
        )

        duration = time.perf_counter() - start_time
        succeeded = sum(1 for r in raw_results if r and r.get("status") == "success")
        failed = len(jobs) - succeeded

        return {
            "total_jobs": len(jobs),
            "succeeded_jobs": succeeded,
            "failed_jobs": failed,
            "runtime_seconds": duration,
            "results": raw_results
        }

    def optimize_batch(
        self,
        jobs: Sequence[Mapping[str, Any]],  # Dict with {"pavement": Pavement, "loads": ..., "traffic_msa": ...}
        num_workers: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancellation_event: Any = None
    ) -> Mapping[str, Any]:
        """Run batch layer optimizations with failure isolation and concurrency."""
        start_time = time.perf_counter()

        def run_single_opt(job: Mapping[str, Any]) -> dict[str, Any]:
            pavement = job["pavement"]
            loads = job["loads"]
            traffic_msa = job["traffic_msa"]
            min_t = job.get("min_thickness_mm", 40.0)
            step = job.get("step_mm", 5.0)
            
            try:
                res = self.design_engine.design_and_optimize(
                    pavement, loads, traffic_msa,
                    min_thickness_mm=min_t, step_mm=step
                )
                return {"status": "success", "result": res}
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        raw_results = execute_parallel(
            func=run_single_opt,
            items=jobs,
            num_workers=num_workers,
            progress_callback=progress_callback,
            cancellation_event=cancellation_event
        )

        duration = time.perf_counter() - start_time
        succeeded = sum(1 for r in raw_results if r and r.get("status") == "success")
        failed = len(jobs) - succeeded

        return {
            "total_jobs": len(jobs),
            "succeeded_jobs": succeeded,
            "failed_jobs": failed,
            "runtime_seconds": duration,
            "results": raw_results
        }
