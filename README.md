# Pavement Lab

A commercial-grade desktop application for **Marshall Mix Design** of bituminous
pavement mixes (DBM, BC, SDAC, BM). The calculation core is a **digital clone**
of a production Excel workbook used by a working highway-materials consultancy
— every computed value matches the source workbook to 1 × 10⁻⁹.

![Status: Engine parity 12/12](https://img.shields.io/badge/Excel%20parity-12%2F12%20passing-2c8a3e)
![Build](https://img.shields.io/badge/Windows%20build-PavementLab.exe%20(31%20MB)-1f3a68)

---

## ⚡ ONE-CLICK LAUNCH (no Python needed)

A standalone Windows executable has already been built and is ready to run.
Nothing else needs installing.

### Option A — Double-click on this machine

1. Open `dist\PavementLab\` and double-click **`PavementLab.exe`**,
2. Or double-click **`Launch.bat`** in the project root,
3. Or open the **Pavement Lab** shortcut that was placed on your Desktop.

### Option B — Hand the build to another Windows PC

A redistributable archive was created at:

```
E:\myclaud project\1\PavementLab-Windows.zip   (~139 MB)
```

Copy that zip to the target PC, unzip it anywhere, open the folder, and
double-click **`PavementLab.exe`**. The bundle embeds Python and every library;
the target machine does **not** need Python installed.

---

## 🛠️ Fresh-machine setup (only needed if rebuilding from source)

```
Setup.bat   ← installs Python (if missing), creates .venv, installs deps,
              optionally builds the .exe
Launch.bat  ← runs the .exe; falls back to "python run.py" if no .exe
Build.bat   ← clean rebuild of the .exe (after Setup.bat has been run once)
```

`Setup.bat` is self-contained: if Python is not on PATH, it downloads and
silently installs Python 3.12 for the current user, then creates `.venv\`,
installs `requirements.txt`, and offers to build the .exe.

---

## What the app does

- **Aggregate gradation** — per-fraction blending vs MoRTH 500-10 spec band
- **Specific gravity** of coarse aggregates (IS 2386 Part III, wire basket),
  fine aggregates (pycnometer), and bitumen (sp. gr. bottle) per IS 1201-1220
- **Combined aggregate Gsb** (harmonic blend)
- **Gmm** by the Rice (vacuum-saturation) method, with Gse and per-Pb Gmm
- **Gmb** of compacted Marshall specimens with 95 % confidence-interval acceptance
- **Marshall stability and flow** with height check, volume correction, and
  per-specimen include/exclude (or correction-factor override)
- **OBC** at 4 % air voids by linear interpolation
- **Properties at OBC** (Gmb, Stability, Flow, VMA, VFB) by interpolation
- **MoRTH compliance check** with mix-type presets (DBM-I/II, BC-I/II, SDAC, BM)
- **6 Marshall design curves** with OBC marker and dashed line
- **Word + PDF report** matching laboratory consultancy report format
- **SQLite project store** — clients, materials, projects, mix designs, reports

---

## Architecture (at a glance)

```
pavement_lab/
├── Launch.bat                  ← one-click launcher
├── Setup.bat                   ← first-time setup (installs Python if needed)
├── Build.bat                   ← rebuild the .exe
├── run.py                      ← Python entry point
├── README.md
├── requirements.txt
├── app/
│   ├── core/          ← pure-python calculation engine (Excel digital clone)
│   ├── graphs/        ← matplotlib charts + OBC overlay
│   ├── reports/       ← python-docx report builder + PDF converter
│   ├── db/            ← SQLAlchemy 2.0 + SQLite
│   ├── ui/            ← PySide6 desktop UI (sidebar + 4 pages + tabs)
│   └── ai_hooks/      ← stubs for future AI recommendations
├── tests/
│   ├── test_excel_parity.py    ← 12 cell-by-cell asserts against source .xlsm
│   └── golden/                  ← extracted fixture from the source workbook
├── build/
│   ├── pavement_lab.spec        ← PyInstaller one-folder spec
│   ├── build_exe.ps1            ← Windows build script (used by Build.bat)
│   └── installer.iss            ← Inno Setup installer script
└── dist/
    └── PavementLab/
        ├── PavementLab.exe      ← THE STANDALONE APP (31 MB)
        └── _internal/           ← embedded Python + libraries
```

---

## Verification (the parity guarantee)

```powershell
.venv\Scripts\python.exe -m pytest tests\test_excel_parity.py -v
```

12 tests, all green. The engine reproduces every cached cell of
`Marshal Mix final 2 (1).xlsm` (gradation, Sp.Gr., Gsb, Gmm, Gse, Gmb,
stability, flow, summary table, OBC) to within 1 × 10⁻⁹.

Sample run (current workbook):

| Pb%  | Gmm    | Gmb    | VIM%   | VMA%   | VFB%   | Stab kN | Flow mm | MQ    |
|------|--------|--------|--------|--------|--------|---------|---------|-------|
| 3.5  | 2.5894 | 2.4428 | 5.660  | 14.453 | 60.840 | 12.220  | 3.360   | 3.637 |
| 4.0  | 2.5686 | 2.4520 | 4.538  | 14.576 | 68.865 | 14.194  | 3.437   | 4.130 |
| 4.5  | 2.5482 | 2.4595 | 3.479  | 14.762 | 76.434 | 16.220  | 3.620   | 4.481 |
| 5.0  | 2.5280 | 2.4464 | 3.229  | 15.660 | 79.382 | 14.253  | 3.760   | 3.791 |
| 5.5  | 2.5082 | 2.4357 | 2.893  | 16.472 | 82.436 | 13.586  | 3.910   | 3.475 |

**OBC = 4.25 %** · Compliance for DBM Grade II: **PASS**.

---

## Building a real installer (.msi-style single-file installer)

The `dist\PavementLab\` folder works as-is. If you want a single setup wizard
(`PavementLab-Setup.exe`):

1. Run `Setup.bat` or `Build.bat` to produce `dist\PavementLab\`.
2. Install **Inno Setup** from https://jrsoftware.org/isinfo.php (free).
3. Open `build\installer.iss` in Inno Setup and click **Compile**.
4. `PavementLab-Setup.exe` appears in `build\` — distribute that single file.

---

## Editing / extending the software

The code is organised so each piece is replaceable without rewiring the rest.

- **Add a mix type** — append a `MixSpec` to `MIX_SPECS` in
  `app/core/compliance.py`. It instantly appears in the project-form dropdown.
- **Change rounding / decimals** — engine carries full precision; rounding is
  done only at the report/UI display layer (`app/reports/word_report.py` and
  `app/ui/widgets/results_panel.py`). Tweak there.
- **Modify a calculation** — every formula is in its own module under
  `app/core/`. After editing, re-run `python -m pytest tests/test_excel_parity.py`
  to confirm Excel parity is still 12/12.
- **Add a report section** — extend the `build_mix_design_docx` function in
  `app/reports/word_report.py`. The helper utilities `_add_table`, `_add_heading`,
  `_add_p` and `_add_image_grid` make it a one-line addition.
- **Customise the UI theme** — edit `app/ui/style.qss`. Restart the app.
- **Wire AI suggestions** — the empty stubs `suggest_obc_optimisation` and
  `detect_anomalies` in `app/ai_hooks/recommendations.py` are called from the
  results panel; replace the bodies with your AI calls.
- **New calculation panel** — add a `QTableWidget`-based tab to
  `app/ui/widgets/inputs_panel.py`, add a `collect()` method that returns an
  engine dataclass, and reference it from `MainWindow._on_compute`.
- **After any change**, run `Build.bat` to rebuild `PavementLab.exe`.

---

## How the Excel parity works

The source workbook (`source_files/Marshal Mix final 2 (1).xlsm`) is parsed once
by `tests/golden/extract_shirdi_dbm.py`, producing `shirdi_dbm.json`. The
parity test (`tests/test_excel_parity.py`) loads that JSON, feeds the inputs
through the engine, and asserts every output matches the cached Excel value
within 1 × 10⁻⁹ absolute tolerance.

Notable Excel quirks reproduced exactly:

- Volume formula uses literal `3.14`, not `math.pi`
- Per-Pb stability/flow averages may exclude specimens (per-row include flag)
- Some "Corrected Stability" values are hand-entered (override field)
- OBC interpolation walks pairs in order, brackets first crossing, falls back
  to closest if no bracket

---

## Roadmap

- [x] **Phase 0** — Analysis, calculation spec, architecture
- [x] **Phase 1** — Engine + Excel-parity tests (1e-9)
- [x] **Phase 2** — Graph engine
- [x] **Phase 3** — Word + PDF report
- [x] **Phase 4** — SQLite database with projects/clients/materials
- [x] **Phase 5** — PySide6 desktop UI
- [x] **Phase 6** — PyInstaller standalone .exe + one-click launcher
- [ ] **Phase 7** — User login + role management + audit log (DB tables in place)
- [ ] **Phase 8** — AI recommendations (interfaces stubbed)
- [ ] **Phase 9** — Cloud sync (architecture allows; not implemented)

---

## Licence

Proprietary — internal use unless otherwise agreed.
