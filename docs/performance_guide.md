# RoadX Solver Performance Guide

This guide details caching structures and concurrency profiles to achieve maximum commercial throughput.

## 1. Calculation Cache Tuning
RoadX relies on a multi-tier memory cache to bypass redundant transfer matrix builds and Bessel function evaluations.
- Default production size: `50,000` items.
- Expected cache hit ratio: `>95%` on iterative optimizations and sweeps.

## 2. Multi-Process Orchestration
For batch runs, the `BatchSolverEngine` dispatches jobs over a spawn worker pool:
- Set `ROADX_LICENSE_TIER=Enterprise` to enable parallel workers.
- Avoid passing non-pickleable lambdas or local functions.

## 3. Profiler Reports
Each run logs phase elapsed durations. Save report outputs using `global_profiler.save_reports()` to trace bottlenecks.
