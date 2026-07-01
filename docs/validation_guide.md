# RoadX Solver Validation Guide

This guide describes the validation framework used to compare RoadX solver outputs against reference benchmark data.

## 1. Parity Framework Architecture

The validation module automates calculations over selected test cases and computes comparative statistics:
- **Root Mean Square Error (RMSE)**
- **Mean Absolute Error (MAE)**
- **Relative Mismatch Percentages**

## 2. Benchmark Case Indexes
Benchmark configurations are loaded via the `BenchmarkDatabase` from official JSON records.
Running the benchmark suite produces:
- `reports/parity/parity_report.md`
- `reports/benchmark/calibration_report.md`

## 3. Trouble-shooting Warnings
If calculations deviate beyond configured tolerances, the runner logs diagnostic suggestions outlining potential causes (e.g. pressure conversions, load radius scaling, or layer index offsets).
