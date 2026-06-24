# Walkthrough - SamPave Expert Audit Verification

This walkthrough documents the validation actions, scripts run, and outcomes for the SamPave Expert Audit.

## Changes Made
No core application code modifications were made, as this is an independent expert validation. We constructed a standalone audit runner under the scratch space to run our benchmark tests and perform mathematical and logical verification checks:
* [expert_audit_runner.py](file:///C:/Users/ASUS/.gemini/antigravity/brain/6ec8bafc-ca13-4f25-a79b-5ec989a123e9/scratch/expert_audit_runner.py)
* [inspect_docx.py](file:///C:/Users/ASUS/.gemini/antigravity/brain/6ec8bafc-ca13-4f25-a79b-5ec989a123e9/scratch/inspect_docx.py)
* [inspect_char.py](file:///C:/Users/ASUS/.gemini/antigravity/brain/6ec8bafc-ca13-4f25-a79b-5ec989a123e9/scratch/inspect_char.py)

The runner evaluated 20 scenarios, comparing SamPave's outputs for traffic cumulative design (MSA) and subgrade resilient modulus ($M_r$) against independent calculations.

## Verification & Outcomes

### 1. Benchmark Scenarios Run
The runner generated two key CSV files inside the repository:
* [EXPERT_AUDIT_BENCHMARK_CASES.csv](file:///E:/pavment%20sam%20pave/validation_reports/EXPERT_AUDIT_BENCHMARK_CASES.csv): Defines 20 test cases representing traffic categories, CBR values, and edge scenarios.
* [EXPERT_AUDIT_RESULT_TABLE.csv](file:///E:/pavment%20sam%20pave/validation_reports/EXPERT_AUDIT_RESULT_TABLE.csv): Displays independent vs SamPave MSA & subgrade $M_r$, layer compositions, and checks.

### 2. Validation Findings
* **Math Precision:** SamPave calculations match independent calculations to **0.00% error** across all cases.
* **Failure bounds:** Core calculation layer blocks negative traffic, design life, zero/negative CBR, and out-of-bounds lane distribution factor safely.
* **IITPAVE Refusal Gate:** Confirmed that when `IITPAVE.exe` is missing, the workflow is blocked gracefully with status `mechanistic_workflow_blocked`, rather than silently falling back to mock numbers or crashing.
* **Word Reports:** Inspecting `scenario_1_report.docx` via python-docx confirmed a professional layout containing 16 tables, with clear units, symbols, and complete provenance traceability. If mechanistic checks are not run, it clearly lists `IITPAVE unavailable` instead of mock values.
* **Pytest Suite:** Ran the full test suite (`pytest`) and verified all **28 tests passed successfully** with no regressions.

## Final Documents Created
* [SAMPAVE_HARSH_EXPERT_AUDIT_REPORT.md](file:///E:/pavment%20sam%20pave/validation_reports/SAMPAVE_HARSH_EXPERT_AUDIT_REPORT.md)
* [SAMPAVE_CLIENT_DEMO_VERDICT.md](file:///E:/pavment%20sam%20pave/validation_reports/SAMPAVE_CLIENT_DEMO_VERDICT.md)

---

## Phase M: Engineering Intelligence Checker

### Changes Made
1. **Core Validation Module:** Created [intelligence_checker.py](file:///E:/pavment%20sam%20pave/app/core/intelligence_checker.py) to implement material placement checks, modular ratio screening, stiffness inversion check (with cover-over-CTB exemption), layer thickness warnings, and Poisson's ratio limits.
2. **Dataclass & Core Integration:** Added `poisson` field to `PavementLayer` and `intelligence` field to `StructuralResult`, `StabilizedResult`, and `CatalogueLookupResult`. Integrated computation calls inside `compute_structural_design`, `compute_stabilized_design`, and `lookup_catalogue_design`.
3. **PySide6 UI:** Added "Engineering Health Check" card to both `structural_panel.py` and `stabilized_panel.py` to display the Screening Score, Risk Level badge, warnings, and notes dynamically.
4. **DPR Word Reports:** Created [intelligence_report.py](file:///E:/pavment%20sam%20pave/app/reports/intelligence_report.py) to write the "Engineering Intelligence Review" section and integrated it into both structural and stabilized standalone reports, as well as the combined Word report builder.

### Verification Run & Outcomes
- **New Unit Tests:** Added 8 cases in [test_intelligence_checker.py](file:///E:/pavment%20sam%20pave/tests/test_intelligence_checker.py) to verify score calculations, modular ratios, stiffness inversions, and material tiers.
- **Pytest Pass:** Ran the full pytest suite. All **49 test cases passed** (100% success rate).
- **Smoke Tests:** Ran UI, export, and stabilized smoke tests successfully. Verified that health check cards display and Word documents export the intelligence review section correctly with the safety disclaimer.
- **EXE Rebuild:** Standalone executable `dist/SamPave/SamPave.exe` successfully rebuilt.

---

## Phase N: IITPAVE Production Mode

### Changes Made
1. **Version Discovery & Probing:** Added `detect_iitpave_version` and `validate_iitpave_environment` inside `app/core/iitpave/installation_manager.py` to check the executable and configure system settings.
2. **Subprocess Runner:** Built a subprocess runner that creates unique, timestamped run folders under the user data directory, retaining execution logs (`iitp_inp.dat`, `iitp_out.dat`, `stdout.log`, `stderr.log`, `run_status.json`).
3. **Safety Verification Modes:** Implemented two distinct validation paths: *Decision Support Mode* (when binary is missing/invalid) and *Mechanistic Verified Mode* (when execution succeeds and fatigue/rutting strain checks complete successfully).

### Verification Outcomes
- **New Unit Tests:** Added pytest assertions under `tests/test_iitpave_production.py` and `tests/test_iitpave_structural_workflow.py`.
- **Pytest Pass:** Verified that all **54 tests passed successfully**.

---

## Phase O: Professional Consultancy Release

### Changes Made
1. **Schema & Migration:** Updated models inside `app/db/schema.py` and added migration code inside `app/db/repository.py` to support locks, checklists, revisions, and consultant/report metadata.
2. **Review Checklist & Clones:** Added `save_project_checklist` for review checks, `duplicate_project` for clones, `create_project_revision` for revision creation, and `compute_project_diff` for tracking parameter updates while ignoring UI noise.
3. **Word DPR & ZIP Deliverables:** Upgraded `app/reports/report_builder.py` with cover page, assumptions sheet, limitations sheet, and sign-off seal placeholders. Integrated submission ZIP packaging inside `app/core/project_archive.py`.
4. **UI Locking Safety Gates:** Added locking safeties and the Submission Center Panel (`app/ui/widgets/submission_center_panel.py`) to manage reviewer tasks.

### Verification Outcomes
- **New Unit Tests:** Built `tests/test_consultancy_release.py`.
- **Pytest Pass:** All **60 pytest cases passed successfully**.
- **Smoke Tests:** Running `smoke_ui.py` succeeded with "SMOKE OK" status.
- **Sample Generation:** Created sample Word reports and ZIP deliverable packages under `validation_reports/`.
