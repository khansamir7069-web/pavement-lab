"""Performance profiling utility for tracking runtime, memory, and cache hit metrics."""
from __future__ import annotations

import contextlib
import json
import os
import time
from typing import Any, Iterator

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class PerformanceProfiler:
    """Internal profiler tracking specific solver and design phases."""

    def __init__(self) -> None:
        self.runtimes: dict[str, float] = {}
        self.start_times: dict[str, float] = {}
        self.memory_start: float = 0.0
        self.memory_peak: float = 0.0
        self.batch_count: int = 0

    def start(self) -> None:
        """Start global profiling session."""
        self.runtimes.clear()
        self.start_times.clear()
        self.memory_start = self._get_memory_mb()
        self.memory_peak = self.memory_start
        self.batch_count = 0
        self.start_time("total")

    def stop(self) -> None:
        """Stop global profiling session."""
        self.stop_time("total")
        current_mem = self._get_memory_mb()
        if current_mem > self.memory_peak:
            self.memory_peak = current_mem

    def start_time(self, phase: str) -> None:
        """Record start timestamp for a named phase."""
        self.start_times[phase] = time.perf_counter()
        current_mem = self._get_memory_mb()
        if current_mem > self.memory_peak:
            self.memory_peak = current_mem

    def stop_time(self, phase: str) -> float:
        """Record end timestamp and accumulate runtime for a named phase."""
        if phase not in self.start_times:
            return 0.0
        duration = time.perf_counter() - self.start_times[phase]
        self.runtimes[phase] = self.runtimes.get(phase, 0.0) + duration
        
        current_mem = self._get_memory_mb()
        if current_mem > self.memory_peak:
            self.memory_peak = current_mem
            
        return duration

    @contextlib.contextmanager
    def measure(self, phase: str) -> Iterator[None]:
        """Context manager to measure runtime of a block of code."""
        self.start_time(phase)
        try:
            yield
        finally:
            self.stop_time(phase)

    def _get_memory_mb(self) -> float:
        """Get current resident memory usage in MB."""
        if _HAS_PSUTIL:
            try:
                process = psutil.Process()
                return process.memory_info().rss / (1024.0 * 1024.0)
            except Exception:
                pass
        
        # Standard library fallback using tracemalloc if active
        import tracemalloc
        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            return peak / (1024.0 * 1024.0)
        return 0.0

    def generate_markdown(self, cache_stats: dict[str, Any], num_workers: int = 1) -> str:
        """Format the profiled statistics as a Markdown document."""
        tot_time = self.runtimes.get("total", 0.0)
        hankel_time = self.runtimes.get("hankel_integration", 0.0)
        matrix_time = self.runtimes.get("transfer_matrix", 0.0)
        opt_time = self.runtimes.get("optimization", 0.0)
        report_time = self.runtimes.get("reporting", 0.0)
        
        throughput = 0.0
        if self.batch_count > 0 and tot_time > 0.0:
            throughput = self.batch_count / tot_time

        lines = [
            "# RoadX Computation Engine Performance Report",
            f"Report generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 1. Runtime Breakdown",
            "",
            "| Phase | Elapsed Time (s) | Percentage |",
            "| :--- | :--- | :--- |",
            f"| **Total Run** | {tot_time:.3f} s | 100.0% |",
            f"| **Hankel Integration** | {hankel_time:.3f} s | {(hankel_time/tot_time*100.0 if tot_time > 0 else 0.0):.1f}% |",
            f"| **Transfer Matrix Solver** | {matrix_time:.3f} s | {(matrix_time/tot_time*100.0 if tot_time > 0 else 0.0):.1f}% |",
            f"| **Layer Thickness Optimization** | {opt_time:.3f} s | {(opt_time/tot_time*100.0 if tot_time > 0 else 0.0):.1f}% |",
            f"| **Report Generation** | {report_time:.3f} s | {(report_time/tot_time*100.0 if tot_time > 0 else 0.0):.1f}% |",
            "",
            "## 2. Resource Utilization",
            f"- **Peak Memory Usage:** {self.memory_peak:.2f} MB",
            f"- **Worker Pool Size:** {num_workers} processes",
            f"- **Batch Job Count:** {self.batch_count} jobs",
            f"- **Throughput Rate:** {throughput:.2f} jobs/sec",
            "",
            "## 3. Intelligent Cache Statistics",
            f"- **Cache Hits:** {cache_stats.get('hits', 0)}",
            f"- **Cache Misses:** {cache_stats.get('misses', 0)}",
            f"- **Cache Hit Ratio:** {cache_stats.get('hit_ratio', 0.0)*100.0:.2f}%",
            f"- **Total Cache Queries:** {cache_stats.get('total_queries', 0)}",
            ""
        ]
        return "\n".join(lines)

    def generate_json(self, cache_stats: dict[str, Any], num_workers: int = 1) -> str:
        """Serialize the profile stats to a JSON string."""
        tot_time = self.runtimes.get("total", 0.0)
        throughput = (self.batch_count / tot_time) if (self.batch_count > 0 and tot_time > 0.0) else 0.0
        
        data = {
            "runtimes": dict(self.runtimes),
            "memory": {
                "start_mb": self.memory_start,
                "peak_mb": self.memory_peak
            },
            "concurrency": {
                "worker_count": num_workers,
                "batch_size": self.batch_count,
                "throughput_jobs_per_sec": throughput
            },
            "cache": dict(cache_stats)
        }
        return json.dumps(data, indent=2)

    def save_reports(
        self,
        cache_stats: dict[str, Any],
        num_workers: int = 1,
        output_dir: str | None = None
    ) -> tuple[str, str]:
        """Save performance Markdown and JSON reports to output_dir."""
        from mechanistic_solver.licensing import active_license, FEATURE_PROFILER_REPORT
        active_license.check_feature(FEATURE_PROFILER_REPORT)
        
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "reports", "performance"
            )
            
        os.makedirs(output_dir, exist_ok=True)
        
        md_content = self.generate_markdown(cache_stats, num_workers)
        json_content = self.generate_json(cache_stats, num_workers)
        
        md_path = os.path.join(output_dir, "performance_report.md")
        json_path = os.path.join(output_dir, "performance_report.json")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_content)
            
        return md_path, json_path


# Global profiler instance
global_profiler = PerformanceProfiler()
