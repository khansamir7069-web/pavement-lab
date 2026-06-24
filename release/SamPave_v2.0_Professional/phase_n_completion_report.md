# Phase N: IITPAVE Production Mode
## Completion Report

This report summarizes the implementation, safety compliance, and verification details of the **IITPAVE Production Mode** (Phase N) in the SamPave Engineering Suite.

---

### 1. Verification Modes & Safety Compliance

As mandated by the safety guidelines, the suite now operates under two distinct verification modes:
*   **Decision Support Mode:** Enabled by default when the IITPAVE executable is missing, invalid, configured for stub/mock execution, fails during run, times out, or when output parser verification checks fail. Stub/mock results are never labeled as verified.
*   **Mechanistic Verified Mode:** Active only when a real, validated `IITPAVE.exe` is configured, successfully completes execution, and the output parser extracts critical strains (fatigue and rutting) successfully.

---

### 2. IITPAVE Installation Manager & Discovery

Implemented in `app/core/iitpave/installation_manager.py` and connected to the UI:
*   **Version Probing:** Safe subprocess probing runs the executable and grabs version headers.
*   **Discovery Engine:** Scans system folders, parent directories, and PATH environment variables.
*   **JSON Persistence:** Automatically reads and writes `iitpave_config.json` containing path, runner mode (production vs stub), process timeouts, and discovery settings.
*   **Validation States:** Probes executable paths to report validation success or errors.

---

### 3. Production Subprocess Execution Engine

Implemented in `app/core/iitpave/runner.py`:
*   **Unique Timestamped Run Folders:** Dedicated directories are created under `USER_DATA_DIR / "iitpave_runs"` (e.g. `run_YYYYMMDD_HHMMSS_ffffff`) to prevent process conflicts.
*   **Execution Timeouts:** Subprocess execution is wrapped with configurable timeouts (default 60 seconds) to prevent frozen threads.
*   **Artifact Retention:** Each run writes five distinct artifacts in the run folder:
    1.  `iitp_inp.dat`: The generated IITPAVE input file.
    2.  `iitp_out.dat`: The generated raw output file.
    3.  `stdout.log`: Console stdout messages.
    4.  `stderr.log`: Console stderr errors.
    5.  `run_status.json`: Contains runtime metadata (status, duration, timestamp, return code, error messages).
*   **Safe Subprocess:** Mock executables and stubs are restricted to automated unit tests and never leak to the real user workflow.

---

### 4. Output Parser & Error Integrity

*   **Integrity Rules:** If execution completes but the output parser fails (e.g. invalid format or unparseable columns), it raises/displays exactly:
    `"IITPAVE execution completed but output verification failed."`
*   **Verification Gate:** Strains are successfully parsed and stored in the database or report fields. If verification fails, the stack remains in *Decision Support Mode*.

---

### 5. UI Integration

*   **IITPAVE Integration Manager Panel (`app/ui/widgets/iitpave_status_panel.py`):**
    *   Visual badges for binary detection state (Detected / Not Detected) and active verification mode (Mechanistic Verified Mode / Decision Support Mode).
    *   Candidates selector (shows discovered binaries) and manual file browser.
    *   Runner configuration options (Timeout seconds, Scan PATH).
    *   Last Run log viewer (renders raw input preview, stdout log, stderr errors, and metadata).
*   **Structural Panel & Stabilized Panel Integration:**
    *   Displays verification status banner inside the results card (green badge for verified, yellow/beige badge for decision support).
    *   Contains interactive links ("IITPAVE Integration Manager") that instantly switch to the settings page to configure the executable.
    *   CTB/CTS stabilized calculations automatically trigger the mechanistic workflow and persist verification data on save.

---

### 6. DPR Word Report Integration

*   **Mechanistic Report (`app/reports/mechanistic_report.py`):**
    *   Includes a dedicated "IITPAVE Integration Details" section highlighting the active Verification Mode and execution timestamp.
    *   Renders a detailed "IITPAVE Analysis Layer Composition" table displaying layer names, material types, thickness, elastic modulus, and custom Poisson's ratios.
*   **Structural Report & Stabilized Report:**
    *   Both standalone and combined reports embed the mechanistic validation summary when verification data is saved.
    *   Includes the active verification mode stamp on all documents.

---

### 7. Verification & Test Metrics

We ran automated verification and smoke test suites:
*   **Unit Tests (`tests/test_iitpave_production.py`):** Covers installation manager persistence, runner logs/artifacts creation, mock success workflow, stub fallback mode, and unparseable output contract failure messages.
*   **Pytest Suite:** All **54 pytest cases passed** successfully (100% success rate).
*   **UI Smoke Test (`smoke_ui.py`):** Passed successfully.
*   **Stabilized Smoke Test (`smoke_stabilized.py`):** Round-trip database, UI, and report checks passed.
*   **Export Smoke Test (`smoke_export.py`):** Word reports successfully built and validated.
*   **PyInstaller Standalone Build:** Executable build completed successfully in `dist/SamPave/SamPave.exe`.
