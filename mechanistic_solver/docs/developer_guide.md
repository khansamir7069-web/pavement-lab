# RoadX Independent Mechanistic Solver — Developer Guide (Phase 3 Part 4A)

This developer guide details the Burmister layered elastic equations derivation, global transfer matrix system layout, and linear solving procedures.

---

## 1. Package Architecture & Sub-modules

The `mechanistic_solver/` package is structured into clean layers separating models, mathematical routines, material records, and evaluation outputs.

### Sub-modules and Stubs:
1. **Core Package (`core/`):**
   - `constants.py`: Centralized physical (Gravity, Pi) and execution limits (Tolerances, max supported layers, default temperature).
   - `units.py`: Unit conversion manager using float64 internally.
   - `models.py`: Structural data models: `Layer`, `Pavement`, `WheelLoad`, and `ObservationPoint`.
   - `validation.py`: Standalone, decoupled validation utilities.
   - `exceptions.py`: Custom semantic engineering exception classes.
2. **Math Package (`math/`):**
   - `numerical.py`: Safe division, clamping, error checking, and casting functions.
   - `bessel.py`: Bessel J0 and J1 polynomial approximations.
   - `integration.py`: Trapezoidal, Simpson, and adaptive Simpson integrations.
   - `transforms.py`: Hankel transform integration skeletons.
3. **Geometry (`geometry/`):**
   - `loads.py` / `tires.py` / `contact_area.py`: Placeholder stubs for multi-load assembly coordinate modeling.
4. **Materials (`materials/`):**
   - `library.py`: Versioned JSON database loaders and presets registries. Defines the abstract `IMaterial` interface.
   - `interpolation.py`: Viscoelastic temperature/frequency curves placeholder.
5. **Solver Engine (`solver/`):**
   - `engine.py`: Defines `MechanisticSolver` entry interface.
   - `kernels/`: `boussinesq.py` (single-layer halfspace analytical solutions) and `multilayer_elastic.py` (multilayer response kernel).
   - `matrix/`:
     - `layer_system.py`: Cumulative depth mapper (`LayerSystem`).
     - `boundary_conditions.py`: Interface bond conditions (`BONDED`, `UNBONDED`, `PARTIAL_BOND`).
     - `coefficient_builder.py`: Stores unknown Burmister integration constants (`LayerCoefficients`).
     - `boundary_equations.py`: Assembles equations coefficient matrices of shape $(4n-2, 4n-2)$ for $n$ layers.
     - `linear_solver.py`: Solves equations system using solve, least-squares, and pseudo-inverse fallbacks.
     - `transfer_matrix.py`: stability reports (`MatrixConditionReport`).
6. **Outputs (`outputs/`):**
   - `response.py`: Standard universal `Response` object container. Supports `status`, `partial_results`, `unsupported_results`, and `method_metadata`.
   - `response_tables.py` / `contour_generator.py`: Tabular formatting and contour grid coordinates generator stubs.
7. **Visualization (`visualization/`):**
   - `cross_section.py` / `stress_plot.py` / `strain_plot.py`: 2D graphing stubs.

---

## 2. Burmister Layered Elastic Formulation

Burmister's theory represents stresses and displacements in a multi-layered elastic system using a stress function $\phi_i$ satisfying the biharmonic equation $\nabla^4 \phi_i = 0$ in each layer $i$. For an axisymmetric load, the stress function in the Hankel domain is:
\[ \phi_i^* = (A_i e^{-m z} + B_i e^{m z} + C_i z e^{-m z} + D_i z e^{m z}) \]
Where $A_i, B_i, C_i, D_i$ are the unknown integration constants, and $m$ is the radial parameter.

---

## 3. Boundary & Interfacial Equations Derivation

To solve the $4n-2$ unknown coefficients (where finite layers have 4 coefficients and the subgrade has 2), we establish boundary conditions in the Hankel domain:

### A. Surface Boundary ($z_1 = 0$ in Layer 1)
1. **Vertical Stress:** $\sigma_{z, 1}^*(0) = -q a \frac{J_1(m a)}{m}$
   \[ m A_1 + m B_1 - 2(1-\nu_1) C_1 + 2(1-\nu_1) D_1 = q a \frac{J_1(m a)}{m^2} \]
2. **Shear Stress:** $\tau_{zr, 1}^*(0) = 0$
   \[ -m A_1 + m B_1 - (1-2\nu_1) C_1 + (1-2\nu_1) D_1 = 0 \]

### B. Interface Continuity ($z_i = h_i$, $z_{i+1} = 0$)
For each interface separating finite layer $i$ and layer $i+1$:
1. **Vertical Stress continuity:** $\sigma_{z, i}^*(h_i) = \sigma_{z, i+1}^*(0)$
2. **Shear Stress continuity:** $\tau_{zr, i}^*(h_i) = \tau_{zr, i+1}^*(0)$
3. **Vertical Displacement continuity:** $w_i^*(h_i) = w_{i+1}^*(0)$
4. **Radial Displacement continuity:** $u_i^*(h_i) = u_{i+1}^*(0)$

### C. Bottom Semi-Infinite Boundary ($z \to \infty$)
As depth $z \to \infty$, stresses and displacements in the subgrade must decay to zero. Therefore, the upward wave coefficients $B_n$ and $D_n$ are set to zero:
\[ B_n = 0, \quad D_n = 0 \]

---

## 4. Matrix Layout ($4n-2 \times 4n-2$)

The system of linear equations is formulated as:
\[ A \cdot x = b \]
Where:
- $A$ is the coefficients matrix of shape $(4n-2, 4n-2)$.
- $x$ is the vector of solved coefficients.
- $b$ is the loading boundary vector of shape $(4n-2,)$.

---

## 5. Current Solver Limitations & Warning
> [!IMPORTANT]
> **Warning on IITPAVE Parity:** The multilayer response evaluation engine is currently experimental/partial and is **NOT** yet validated for full IITPAVE parity.
> The numerical evaluation of inverse Hankel integration under general layered configurations is subject to ongoing validation. Responses should be treated as experimental.

- **Bonded interface only:** Frictionless and slip boundaries are not solved.

---

## 6. Integration Status
Phase 3 Part 4B has implemented:
1. Inverse Hankel transform integration algorithms utilizing SciPy quadrature and adaptive Simpson fallback.
2. Computation of stresses, strains, and deflections at any depth.
3. Verification of unit consistency, monotonic sanity, and schema layout.

Phase 3 Part 4C has implemented:
1. **IITPAVE Output Parser:** Parses standard `.OUT` / `.txt` files to extract critical strains, stresses, and deflection tables.
2. **Parity Runner & Metrics:** Automates running multilayer cases, comparing results against expected IITPAVE values, and calculating MAE, RMSE, absolute/relative errors, and tolerance checks.
3. **Parity Reports:** Automatically generates Markdown (`parity_report.md`) and JSON (`parity_report.json`) summaries under `reports/parity/`.

Phase 3 Part 5 has implemented:
1. **Official Benchmark Database (`BenchmarkDatabase`):** Automatically discovers and indexes case `.json` configurations and matching `.out` files under the `tests/fixtures/iitpave/official/` sub-folder.
2. **Benchmark Runner (`BenchmarkRunner`):** Batch executes benchmark cases, executes RoadX solver calculations, evaluates custom tolerances, and computes per-case validation statuses.
3. **Engineering Troubleshooting Hints:** Runner performs heuristics to identify mismatches (unit mismatch factor of $10^6$ or $1000$, inconsistent wheel load/radius configuration, incorrect layer ordering, and depth indexing mismatches) without modifying math equations.
4. **Validation Statistics (`BenchmarkStatistics`):** Aggregates errors globally to compute MAE, RMSE, MAPE, standard deviation, and 95th percentile errors.
5. **Calibration Reports (`CalibrationReportGenerator`):** Exports results as Markdown (`calibration_report.md`), JSON (`calibration_report.json`), and CSV (`calibration_report.csv`) formats under `reports/benchmark/`.

---

## 7. How to Add Benchmark Files & Run Validation

1. **Add Official Benchmarks:** Place the benchmark `.OUT` file and its matching `.json` input file in `mechanistic_solver/tests/fixtures/iitpave/official/`.
2. **Run Validation Batch:**
   ```python
   from mechanistic_solver.validation import BenchmarkDatabase, BenchmarkRunner, BenchmarkStatistics, CalibrationReportGenerator
   
   db = BenchmarkDatabase()
   cases = db.discover_cases()
   
   runner = BenchmarkRunner()
   records = runner.run_batch(cases)
   
   stats = BenchmarkStatistics().aggregate(records)
   CalibrationReportGenerator().save_reports(records, stats, "mechanistic_solver/reports/benchmark/")
   ```

> [!WARNING]
> **Solver Maturity Status:** Overall solver maturity remains `EXPERIMENTAL` by default. It is not promoted to `VALIDATED` until official benchmark datasets are ingested and all cases successfully pass the configured tolerances.

---

## 8. Calibration & Accuracy Guidelines
* **Tolerances:** Tolerances are fully configurable per-case in the input `.json` schema (typically $\pm 5.0$ microstrain for strains, $\pm 0.05$ mm for deflection, and $\pm 0.01$ MPa for stresses).
* **No Artificial Tuning:** Downstream developers must never hardcode scaling factors or artificially tune solver equations to enforce parity. Mismatches must be investigated to trace underlying mathematical/matrix model causes.
