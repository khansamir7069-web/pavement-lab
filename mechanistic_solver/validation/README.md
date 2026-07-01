# RoadX Multilayer Solver Validation & Calibration Sub-Package

This sub-package contains the validation and calibration pipeline used to benchmark the RoadX layered elastic solver responses against IITPAVE outputs.

## 1. Folder Structure

Benchmark test cases are discovered and loaded under the test fixtures directories:

```text
mechanistic_solver/tests/fixtures/iitpave/
    ├── sample_iitpave_output.out
    ├── sample_iitpave_expected.json
    └── official/
         ├── README.md
         ├── case1.json           <-- Input metadata and expected outputs
         └── case1.out            <-- Raw IITPAVE text output file
```

- **`official/` Sub-folder:** Contains actual benchmark cases derived from official IITPAVE installations. Case configurations placed directly in the parent directory are considered templates/samples.

> [!WARNING]
> **No committed datasets:** No official IITPAVE datasets are committed to this repository. You must obtain official `.OUT` files and corresponding `.json` configurations and place them under `official/` to run a validation check.

---

## 2. Ingest Case Format

Each validation case requires a matching JSON configuration and a raw output file:

### A. Case JSON configuration (`<case_id>.json`)
```json
{
  "inputs": {
    "layers": [
      {
        "name": "Bituminous Layer",
        "thickness": 100.0,
        "elastic_modulus": 3000.0,
        "poisson_ratio": 0.35,
        "density": 2400.0
      }
    ],
    "subgrade": {
      "name": "Subgrade Soil",
      "thickness": null,
      "elastic_modulus": 60.0,
      "poisson_ratio": 0.4,
      "density": 1800.0
    },
    "loads": [
      {
        "wheel_load": 40.0,
        "pressure": 0.56,
        "radius": 150.0
      }
    ]
  },
  "observation_points": [
    { "x": 0.0, "y": 0.0, "z": 100.0 }
  ],
  "expected_iitpave_outputs": {
    "tensile_strain_microstrain": 120.0,
    "vertical_strain_microstrain": 220.0,
    "vertical_stress_mpa": 0.45,
    "deflection_mm": 0.85
  },
  "tolerance_limits": {
    "epsilon_t_bottom_bituminous": { "abs": 5.0, "rel": 0.05 },
    "epsilon_v_top_subgrade": { "abs": 5.0, "rel": 0.05 }
  },
  "notes": "Official IRC:37 Annexure-I example case"
}
```

### B. IITPAVE Raw Output file (`<case_id>.out` / `<case_id>.txt`)
Standard text output from IITPAVE featuring the header columns:
`Z R SigmaZ SigmaT SigmaR TaoRZ DispZ epZ epT epR`
followed by numerical response rows.

---

## 3. Engineering Diagnostics

If a validation case fails, the `BenchmarkRunner` automatically analyzes the outputs to identify possible engineering causes:
* **Unit mismatch:** Mismatches of exactly $10^6$ or $1000$ (e.g. strain vs microstrain, Pa vs MPa, meters vs millimeters).
* **Load configuration mismatches:** Modulus or Poisson values out of normal bounds, or inconsistent wheel load/tyre pressure calculations.
* **Recommendations:** Troubleshooting tips are written directly into the markdown and JSON calibration reports. Heuristics only provide suggestions and **never** modify solver equations automatically.
