# Checkpoint 1 Validation Report: Repository Status

This report documents the status and completeness of the SamPave Engineering Suite repository.

## 1. Repository Metadata

* **Current Branch:** `main`
* **Latest Commit Hash:** `54fee85348b6a0b8367e03d12c5ebcdc52f10c8b`
* **Latest Commit Message:** `phase 51 remove default seeded mix input values`
* **Latest Commit Author:** Samir Khan <sambhai965@gmail.com>
* **Latest Commit Date:** Tue May 19 15:03:32 2026 +0530

## 2. Recent Commit History

```
54fee85 phase 51 remove default seeded mix input values
3262852 phase 50 UI fix dynamic material controls
a306c72 phase 50 dynamic mix material selection
52cba3b fix structural IITPAVE visible fallback
c082b7a integrate IITPAVE structural workflow
```

## 3. Project Structure and Main Folders

* **`app/`**: Core application source code
  * **`core/`**: Mathematical calculations, design algorithms, IITPAVE orchestration, database schemas.
  * **`data/`**: JSON specification files (mix types, binder grades, code references).
  * **`db/`**: Schema definition and SQLite repository layer.
  * **`graphs/`**: Plotting logic for Marshall curves (matplotlib, scipy).
  * **`reports/`**: Microsoft Word (.docx) report builders.
  * **`ui/`**: Qt widgets, panels, and layouts (PySide6).
* **`build/`**: PyInstaller spec files and packaging configurations.
* **`docs/`**: Project documentation.
* **`tests/`**: Parity tests, headless smoke tests, and validation scripts.
* **`run.py`**: Entry point launcher.
* **`requirements.txt`**: Python dependencies list (manually updated to include missing `scipy`).
* **`Setup.bat` / `Launch.bat` / `Build.bat`**: Environment creation, app runner, and EXE build scripts.

## 4. Application Framework & Stack

* **Language:** Python 3.14.4
* **GUI Framework:** PySide6 (Qt for Python)
* **Database Layer:** SQLAlchemy 2.0 (SQLite)
* **Mathematical / Graphical Engines:** NumPy, SciPy (for cubic spline curve fitting), Matplotlib
* **Reporting Engines:** python-docx, reportlab, openpyxl

## 5. How to Run the Application

The application is run by executing:
1. **Source Launch (Venv):** `.venv\Scripts\python.exe run.py` or double-clicking `Launch.bat` (which automatically locates the virtual environment python interpreter).
2. **Standalone Build:** Run the compiled binary located at `dist\SamPave\SamPave.exe` (after building).

## 6. Existing Test Suites

* **Excel Parity Tests:** `tests/test_excel_parity.py` (16 tests verifying math parity with Marshal Mix XLSM).
* **IITPAVE Workflow Tests:** `tests/test_iitpave_structural_workflow.py` (3 tests verifying parser and runner diagnostic).
* **Dynamic Material Tests:** `tests/test_mix_dynamic_material_selection.py` (4 tests verifying dynamic mix selection rules).
* **Structural Panel Tests:** `tests/test_structural_panel_compute_render.py` (2 tests).
* **Integrated Smoke/Validation Harness:** `tests/pytest_smoke.py` (aggregates 47 smoke test modules and 5 validation sample test projects).

## 7. Packaging and Build Files

* **Spec File:** `build/pavement_lab.spec` and `build/installer/pyinstaller.spec`.
* **Build Script:** `Build.bat` runs PyInstaller on the spec file to compile a standalone executable.
* **Installer Setup:** Per-user installation configs and path checks.

---
**Status of Checkpoint 1:** COMPLETED
