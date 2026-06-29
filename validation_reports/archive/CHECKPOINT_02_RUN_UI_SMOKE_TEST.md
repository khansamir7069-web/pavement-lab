# Checkpoint 2 Validation Report: Run & UI Smoke Test

This report documents the startup validation, environment checks, and UI smoke testing of the SamPave Engineering Suite.

## 1. Environment Verification

* **Python Interpreter:** Python `3.14.4` (PASS)
* **Virtual Environment:** Validated at `.venv/` (PASS)
* **Required Dependencies:** Installed via `requirements.txt`. 
  * *Discovered Bug:* `scipy` was missing from `requirements.txt` but imported in `app/graphs/marshall_charts.py` for cubic spline rendering of Marshall Curves. This caused a `ModuleNotFoundError` during report generation / smoke testing.
  * *Correction:* `scipy>=1.10` was manually added to `requirements.txt` and successfully installed.

## 2. Run Application from Source

* **Startup Command:** `.venv\Scripts\python.exe run.py` (App main entry)
* **Automated Smoke Command:** `.venv\Scripts\python.exe tests/smoke_ui.py` (Native Qt headless driver)
* **UI Launch Status:** SUCCESS. The MainWindow widget constructs successfully, loads QSS styling, and starts the event loop.

## 3. UI Smoke & Navigation Test

Each of the following views has been programmatically and structurally verified:

* **Main Dashboard (`dashboard`):** Loads existing projects, contains cascade-delete and import/export triggers. (PASS)
* **Project Form (`project`):** Optional mix selection, VG-30/CRMB binder grade dialogs, fields write and validate. (PASS)
* **Module Hub (`hub`):** Unified router card layout routing users to individual design sections. (PASS)
* **Mix Design Inputs (`inputs`):** Dynamic gradation envelope tables matching chosen spec type. (PASS)
* **Traffic / MSA Panel (`traffic`):** LDF and VDF presets selection. (PASS)
* **Structural Design Panel (`structural`):** Thickness selection and IITPAVE integration panel. (PASS)
* **Maintenance Panel (`maintenance`):** Sub-tabs for BBD Overlay, Cold Mix, and Micro Surfacing. (PASS)
* **Material Quantity Panel (`material_qty`):** Material bill of quantities calculation. (PASS)
* **Condition Survey Panel (`condition`):** Cracking/distress severity entries and PCI computation. (PASS)
* **Results & Report Panel (`results`):** Computes Marshall parameters and provides PDF/Word export. (PASS)
* **Specifications Editor (`specs_admin`):** Spec limits administrator view. (PASS)

## 4. Navigation & Signal Integrity

* Sidebar list navigation successfully routes the QStackedWidget pages.
* Back buttons on headers are correctly wired using Qt lambdas (`*_` args safety) to return users to the Hub or Dashboard.
* Main window routers handle `saved` signals, updating database states and project statuses (`empty` -> `in_progress` -> `complete`).

## 5. Log & Console Review

* **Errors:** None. Boot and runtime exceptions are absent after the `scipy` dependency correction.
* **Warnings:** 
  ```
  E:\pavment sam pave\app\db\schema.py:25: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    return datetime.utcnow()
  ```
  This warning does not block execution and can be ignored for demo purposes.

---
**Status of Checkpoint 2:** PASS (post-scipy patch)
