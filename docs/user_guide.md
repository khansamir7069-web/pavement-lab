# RoadX Solver User Guide

This guide introduces structural model setup, execution, and output report options for pavement engineers.

## 1. Setting Up Input Models

The solver operates on standard Python datatypes under `mechanistic_solver.core.models`:

```python
from mechanistic_solver.core.models import Layer, Pavement, WheelLoad, ObservationPoint

# Define layer stack (from top to bottom)
l1 = Layer(name="BC", thickness=40.0, elastic_modulus=3000.0, poisson_ratio=0.35)
l2 = Layer(name="DBM", thickness=100.0, elastic_modulus=3000.0, poisson_ratio=0.35)
subgrade = Layer(name="Subgrade", thickness=None, elastic_modulus=60.0, poisson_ratio=0.40)

pavement = Pavement(layers=(l1, l2), subgrade=subgrade)

# Define axle wheel configurations
load = WheelLoad(wheel_load=40.0, pressure=0.56, radius=150.0)

# Specify observation coordinate depths
points = [
    ObservationPoint(r=0.0, z=40.0),   # Bottom of BC
    ObservationPoint(r=0.0, z=140.0)   # Top of Subgrade
]
```

## 2. Running a Solver Case

```python
from mechanistic_solver.solver.engine import MechanisticSolver

solver = MechanisticSolver(mode="multilayer")
response = solver.solve(pavement, [load], points)

# Display stresses and strains
print("Vertical deflection:", response.surface_deflection)
for i, strain in enumerate(response.strain_results):
    print(f"Point {i} Strains: {strain}")
```

## 3. Interpreting Output Reports
All design and optimization runs save detailed Markdown and JSON reports in `reports/design/`. Review the pass/fail verdicts, utilization ratios, and reinforcement recommendations directly inside `design_report.md`.
