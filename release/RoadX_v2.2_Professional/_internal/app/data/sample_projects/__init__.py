"""Phase-16 canonical sample projects + loader.

Each ``corpus_NN_*.json`` in this directory is a self-contained engineering
fixture exercised by ``tests/validation_harness.py``. JSONs ship the
inputs, optional calibration overrides, and an ``expected`` block with
category-level fast-fail assertions; the full deterministic snapshot
lives in ``tests/golden/sample_projects/<name>.expected.json``.
"""
from .loader import list_samples, load_sample, sample_dir

__all__ = ["list_samples", "load_sample", "sample_dir"]
