"""Parallel processing library supporting multiprocessing execution with sequential fallback."""
from __future__ import annotations

import multiprocessing
import os
from typing import Any, Callable, Sequence


def _run_parallel_task(func: Callable[[Any], Any], item: Any) -> Any:
    """Module-level task wrapper for pickling safety in multiprocessing."""
    return func(item)


def execute_parallel(
    func: Callable[[Any], Any],
    items: Sequence[Any],
    num_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancellation_event: Any = None
) -> list[Any]:
    """Execute a function over items in parallel or sequentially.

    Handles cancellation, workers configuration, and falls back to sequential execution on errors.
    """
    total = len(items)
    results: list[Any] = [None] * total

    explicit_parallel = (num_workers is not None and num_workers > 1)

    # Determine workers count
    if num_workers is None:
        from mechanistic_solver.licensing import active_license, FEATURE_PARALLEL_EXECUTION
        if active_license.is_feature_allowed(FEATURE_PARALLEL_EXECUTION):
            try:
                num_workers = min(os.cpu_count() or 1, 4)
            except Exception:
                num_workers = 1
        else:
            num_workers = 1
            
    # Check license feature if parallel is explicitly requested
    if explicit_parallel:
        from mechanistic_solver.licensing import active_license, FEATURE_PARALLEL_EXECUTION
        active_license.check_feature(FEATURE_PARALLEL_EXECUTION)

    # Fallback to sequential if worker count <= 1
    if num_workers <= 1:
        for idx, item in enumerate(items):
            if cancellation_event and cancellation_event.is_set():
                break
            results[idx] = func(item)
            if progress_callback:
                progress_callback(idx + 1, total)
        return results

    # Multiprocessing execution
    # Using Pool with imap_unordered or map
    ctx = multiprocessing.get_context("spawn")
    pool = ctx.Pool(processes=num_workers)
    
    try:
        # Wrap items with index to maintain deterministic ordering
        indexed_items = list(enumerate(items))
        
        # Helper target function
        def target_wrapper(indexed_item: tuple[int, Any]) -> tuple[int, Any]:
            i, it = indexed_item
            res = func(it)
            return i, res

        # Run with imap to support chunking and progress callbacks
        completed = 0
        for i, res in pool.imap_unordered(target_wrapper, indexed_items, chunksize=1):
            if cancellation_event and cancellation_event.is_set():
                pool.terminate()
                break
            results[i] = res
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
                
        pool.close()
        pool.join()
    except Exception:
        pool.terminate()
        pool.join()
        # Fallback to sequential execution on failure
        completed = 0
        for idx, item in enumerate(items):
            if cancellation_event and cancellation_event.is_set():
                break
            results[idx] = func(item)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
                
    return results
