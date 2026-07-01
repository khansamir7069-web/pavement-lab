"""Cloud Solver batch job submission, queue status machine, and retry executor."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from mechanistic_solver.core.models import Pavement, WheelLoad, ObservationPoint
from mechanistic_solver.solver.engine import MechanisticSolver


@dataclass
class CloudJob:
    """Represents an execution job submitted to the cloud queue."""
    job_id: str
    pavement: Pavement
    loads: Sequence[WheelLoad]
    points: Sequence[ObservationPoint]
    status: str = "SUBMITTED"  # SUBMITTED, RUNNING, COMPLETED, FAILED
    retry_count: int = 0
    max_retries: int = 3
    result: Any | None = None
    error_log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class CloudSolverSystem:
    """Manages multi-tenant cloud solver queues, jobs, and fault-tolerant executions."""

    def __init__(self, solver: Any = None) -> None:
        self.solver = solver or MechanisticSolver(mode="multilayer")
        self.jobs: dict[str, CloudJob] = {}

    def submit_job(
        self,
        pavement: Pavement,
        loads: Sequence[WheelLoad],
        points: Sequence[ObservationPoint],
        max_retries: int = 3
    ) -> str:
        """Create and queue a solver job."""
        job_id = str(uuid.uuid4())
        job = CloudJob(
            job_id=job_id,
            pavement=pavement,
            loads=loads,
            points=points,
            max_retries=max_retries
        )
        self.jobs[job_id] = job
        return job_id

    def get_job(self, job_id: str) -> CloudJob | None:
        """Retrieve a queued or completed job."""
        return self.jobs.get(job_id)

    def process_next_job(self) -> str | None:
        """Process the first pending job in the queue, handling retries on failure."""
        pending = [j for j in self.jobs.values() if j.status in ("SUBMITTED", "RUNNING")]
        if not pending:
            return None
            
        job = min(pending, key=lambda x: x.created_at)
        job.status = "RUNNING"
        
        try:
            # Deterministic solver execution
            resp = self.solver.solve(job.pavement, job.loads, job.points)
            job.result = {
                "deflection_mm": resp.surface_deflection,
                "strains": resp.strain_results,
                "stresses": resp.stress_results
            }
            job.status = "COMPLETED"
        except Exception as e:
            job.retry_count += 1
            job.error_log.append(f"Retry {job.retry_count} failed: {e}")
            if job.retry_count >= job.max_retries:
                job.status = "FAILED"
            else:
                job.status = "SUBMITTED"  # Re-queue
                
        return job.job_id
