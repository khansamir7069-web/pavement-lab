# RoadX Solver API Documentation

This document describes the public interface classes and methods of the RoadX Mechanistic Solver.

## 1. Class: `MechanisticSolver`
`from mechanistic_solver.solver.engine import MechanisticSolver`

Main entry point for multilayer elastic calculations.

### Methods:
- `solve(self, pavement: Pavement, loads: Sequence[WheelLoad], observation_points: Sequence[ObservationPoint]) -> Response`:
  Executes integration, solves transfer matrices, and returns stresses/strains.

---

## 2. Class: `IRC37DesignEngine`
`from mechanistic_solver.design.irc37_engine import IRC37DesignEngine`

Handles design calculations, adequacy checking, and reports saving.

### Methods:
- `analyze(self, pavement: Pavement, loads: Sequence[WheelLoad], traffic_msa: float) -> Mapping[str, Any]`:
  Runs solver and checks fatigue/rutting allowable reps.
- `design_and_optimize(self, pavement: Pavement, loads: Sequence[WheelLoad], traffic_msa: float, output_dir: str | None = None) -> Mapping[str, Any]`:
  Optimizes bituminous thickness and saves reports.

---

## 3. Class: `BatchSolverEngine`
`from mechanistic_solver.optimization.batch_solver import BatchSolverEngine`

Orchestrates multi-job execution with parallel pools.

### Methods:
- `solve_batch(self, jobs: Sequence[Mapping[str, Any]], num_workers: int | None = None) -> Mapping[str, Any]`:
  Executes batch solves with progress callbacks.
