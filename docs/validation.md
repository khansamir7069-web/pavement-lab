# PavementLab Validation Framework (Phase 16)

This document describes the canonical sample-project corpus, the
validation harness that exercises it, and the discipline that keeps
placeholder calibration honest.

## Layout

```
app/data/sample_projects/                Canonical inputs (JSON).
  loader.py                              list_samples / load_sample.
  corpus_NN_<name>.json                  One sample = one engineering scenario.

tests/golden/sample_projects/            Deterministic expected snapshots.
  corpus_NN_<name>.expected.json         Category-level signature only.

tests/validation_harness.py              Pipeline runner + bless / assert mode.
tests/pytest_smoke.py                    Aggregator (phase smokes + samples).
```

## Sample shape

Each `corpus_NN_*.json` carries:

```jsonc
{
  "name": "corpus_NN_<short>",
  "description": "...",
  "engineering_intent": "Why this sample exists.",
  "condition": { ... ConditionSurveyInput ... },
  "traffic":   { ... TrafficInput          ... },
  "structural":{ ... StructuralInput       ... },
  "mechanistic": {
    "include": true,
    "is_placeholder": false,
    "source": "external_exe" | "stub",
    "epsilon_t_microstrain": 180.0,
    "epsilon_v_microstrain": 350.0,
    "design_msa_override": null,
    "c_factor": 1.0,
    "structure": { "layers": [ ... PavementStructure ... ] }
  },
  "calibration_overrides": {
    "rehab_thresholds":     { ... RehabThresholds | null ... },
    "fatigue_calibration":  { ... FatigueCalibration | null ... },
    "rutting_calibration":  { ... RuttingCalibration | null ... }
  },
  "expected": {
    "condition":   { "pci_band": "Excellent" | "Good" | "Fair" | "Poor" | "Very Poor" },
    "traffic":     { "msa_band": "very_low" | "low" | "mid" | "heavy" },
    "mechanistic": {
      "refused": false,
      "fatigue_verdict": "PASS" | "FAIL" | null,
      "rutting_verdict": "PASS" | "FAIL" | null
    },
    "rehab": {
      "categories_must_include": [ "..." ],
      "categories_must_exclude": [ "..." ]
    }
  }
}
```

The `expected` block is a fast-fail engineering-intent assertion. The
**full** deterministic snapshot lives separately in
`tests/golden/sample_projects/<name>.expected.json` and is the
regression contract.

## Adding a new sample

1. Drop a `corpus_NN_<name>.json` next to the existing ones.
2. Fill in inputs + engineering intent.
3. (Optional) Specify any `calibration_overrides`.
4. Write the `expected` fast-fail block — this is the engineer's
   contract on what the sample is *supposed* to demonstrate.
5. Bless the golden snapshot:

   ```bash
   PAVEMENT_LAB_BLESS_GOLDENS=1 python -m tests.validation_harness
   ```

6. Inspect the generated `.expected.json` and confirm it matches your
   intent before committing.
7. Run normally to confirm assertion-mode passes:

   ```bash
   python -m tests.validation_harness
   ```

## Calibration swapping

`calibration_overrides` lets a sample exercise the swappable
calibration containers introduced by Phases 10 / 12 / 14:

| Override key           | Engine target                   | Setter                          |
|------------------------|----------------------------------|---------------------------------|
| `rehab_thresholds`     | `app.core.rehab_engine`         | `set_rehab_thresholds`          |
| `fatigue_calibration`  | `app.core.mechanistic_validation` | `set_fatigue_calibration`     |
| `rutting_calibration`  | `app.core.mechanistic_validation` | `set_rutting_calibration`     |

The harness applies overrides BEFORE the pipeline runs and ALWAYS
restores the prior calibration in a `finally` block — even on
assertion failure — so subsequent samples are never tainted.

`corpus_05_calibrated.json` demonstrates the canonical pattern: the
same Fair-PCI / mid-MSA inputs as `corpus_02` produce a different
recommendation set (`overlay + surface_treatment` instead of
`crack_sealing + micro_surfacing + surface_treatment`) and a flipped
fatigue verdict (`FAIL` instead of `PASS`) once `pci_fair_min` is
raised to 65 and `k1` is tightened by 10x.

## Validation philosophy

### 1. Categories, not numbers

Every numeric constant in the engine is currently flagged
`IRC37_PLACEHOLDER` / `placeholder`. Locking snapshots to raw float
values would be **fake precision** — a one-decimal-place tweak in a
calibration constant during real field calibration would torpedo the
test suite for the wrong reason.

The snapshot therefore captures **engineering categories**:

| Surface         | Snapshot field                   | Granularity                                      |
|-----------------|----------------------------------|--------------------------------------------------|
| Condition       | `pci_band`                       | `Excellent` / `Good` / `Fair` / `Poor` / `Very Poor` |
| Traffic         | `msa_band`                       | `very_low` (≤1) / `low` (≤5) / `mid` (≤30) / `heavy` |
| Structural      | `thickness_band`                 | `thin` (<300 mm) / `medium` (300–500) / `thick` (>500) |
| Mechanistic     | `fatigue_verdict / rutting_verdict` | `PASS` / `FAIL` / `null` (refused)             |
| Rehab           | `categories` (sorted set)        | TC_* canonical strings                           |
| Refusal         | `refused`                        | bool                                             |
| Placeholder    | `is_placeholder`                 | bool (propagates through every layer)            |

### 2. No silent fallbacks

The harness **never** substitutes a default when input is missing — a
KeyError or assertion failure must surface. Engineering decisions
made silently are unreviewable.

### 3. Refusal is not failure

When `MechanisticResult.is_placeholder=True`, the Phase-14 refusal gate
fires and both verdicts come back as `null`. The snapshot captures this
as `"fatigue_verdict": null, "rutting_verdict": null, "refused": true`
— this is the **correct** behaviour and is exactly what we assert. A
sample that asserts `refused: true` therefore validates the safety
contract, not a bug.

### 4. Calibration restoration is part of the contract

Every sample's calibration overrides are restored after the pipeline
runs, win or lose. This is enforced in `validation_harness.run_pipeline`
via try/finally.

## Running the suite

```bash
# All samples, assertion mode (CI-style):
python -m tests.validation_harness

# One sample:
python -m tests.validation_harness corpus_05_calibrated

# Bless / re-bless ALL goldens (use deliberately):
PAVEMENT_LAB_BLESS_GOLDENS=1 python -m tests.validation_harness

# Aggregated pytest run (every phase smoke + every sample):
pytest tests/pytest_smoke.py -q
```

`pytest tests/pytest_smoke.py` is the recommended one-line CI invocation
once Phase 17 / installer work begins. Each smoke runner remains
runnable individually via `python -m tests._smoke_phaseNN_*`.

## Discipline (Phase 16 contract)

- **Additive only.** Phase-16 tooling never mutates engine behaviour.
- **No fake authoritative outputs.** Snapshots capture banded
  categories; they never lock raw numeric values produced by
  placeholder calibration.
- **Placeholder traceability.** `is_placeholder=True` propagates
  through every snapshot layer that touches a placeholder calibration.
- **Refusal is a feature.** Stub / placeholder mechanistic input must
  produce `refused: true` — verified by sample fixtures whenever
  `mechanistic.is_placeholder=true` is configured.
- **Calibration restored.** Overrides applied per-sample are restored
  before the next sample runs.
