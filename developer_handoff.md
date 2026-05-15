# Pavement Lab — Developer Handoff

**Project root:** `E:\myclaud project\1\pavement_lab`
**Last checkpoint:** End of Phase 4 (Structural Design skeleton).
**Stack:** Python 3.14, PySide6, SQLAlchemy 2.0 (SQLite), python-docx, matplotlib, PyInstaller 6.20.
**Excel source of truth:** `Marshal Mix final 2 (1).xlsm` (calculations verified to 1×10⁻⁹).

---

## 1. Completed Phases

| # | Name | Status |
|---|---|---|
| 1 | Modular navigation + project / module separation | ✅ |
| 2 | Dynamic specification database (JSON-backed) | ✅ |
| 3 | Binder grade system | ✅ |
| 4 | Independent Structural Design module — skeleton | ✅ |

**Safety gate after EVERY change:**
```
python -m pytest tests/test_excel_parity.py -q   # must show 16 passed
```

---

## 2. Current Architecture

```
app/
├── core/                          # Pure-Python engine — DO NOT REFACTOR
│   ├── compliance.py              # JSON-backed MIX_SPECS + MIX_TYPES
│   ├── binders.py                 # JSON-backed BINDER_GRADES
│   ├── structural_design.py       # Phase 4 — IRC:37 skeleton
│   ├── material_calc.py, gmb.py, gmm.py, gradation.py,
│   ├── marshall.py, obc.py, specific_gravity.py, stability_flow.py,
│   ├── interpolation.py, models.py, import_summary.py
│
├── data/                          # JSON spec data (editable)
│   ├── mix_specs.json             # 25 mix types
│   └── binder_grades.json         # 10 binder grades
│
├── db/
│   ├── schema.py                  # ORM models
│   └── repository.py              # Database facade + _migrate_schema()
│
├── ui/
│   ├── main_window.py             # Central router; stack pages keyed by string
│   └── widgets/
│       ├── common.py              # PageHeader.enable_back(handler) ← reuse
│       ├── dashboard.py           # Has Delete button + Modules column
│       ├── project_form.py        # mix_type optional + binder_grade dialog
│       ├── module_hub.py          # 6 cards → module_selected(key) signal
│       ├── inputs_panel.py        # Mix-design 6 tabs (DO NOT REFACTOR)
│       ├── results_panel.py       # Results + Word/PDF
│       ├── spec_admin.py          # Phase 2 — Marshall-criteria editor
│       └── structural_panel.py    # Phase 4 — IRC:37 input + result
│
├── reports/word_report.py         # ReportContext includes binder fields
├── graphs/marshall_charts.py      # Marshall charts (DO NOT REFACTOR)
├── ai_hooks/recommendations.py    # Heuristic suggestions (unused at runtime)
├── config.py                      # APP_DIR / USER_DATA_DIR / DB_PATH
└── main.py                        # App entry

tests/
├── test_excel_parity.py           # 16 parity tests — SACRED
├── golden/shirdi_dbm.json         # Golden values from Excel
├── smoke_ui.py, smoke_export.py
build/pavement_lab.spec             # PyInstaller spec
run.py, requirements.txt, Setup.bat, Launch.bat, Build.bat
```

**Routing pattern:** `MainWindow._show_page(key)` switches QStackedWidget. Page keys:
`dashboard | project | hub | inputs | results | specs_admin | structural`.

**Back button pattern (every page):**
```python
hdr.enable_back(lambda *_, t=target: self._show_page(t))
# the *_ swallows Qt's clicked(bool) positional arg
```

---

## 3. Important Files (touch carefully)

| File | Sensitivity | Notes |
|---|---|---|
| `app/core/*.py` (10 engine files) | **HIGH** | Parity tests guard these. Only add new files, never refactor. |
| `app/core/compliance.py` | HIGH | Mutates `MIX_SPECS` + `MIX_TYPES` in place. Don't reassign. |
| `app/db/schema.py` | MEDIUM | Only ADD tables/columns. Never remove or rename. |
| `app/db/repository.py` | MEDIUM | Add `ALTER TABLE` lines in `_migrate_schema()` for new columns. |
| `app/ui/main_window.py` | **HIGH** | Most-touched. Central routing. |
| `app/reports/word_report.py` | MEDIUM | Additive only. `ReportContext` is `frozen=True, slots=True`. |
| `tests/test_excel_parity.py` | **NEVER MODIFY** | Golden safety net. |
| `tests/golden/shirdi_dbm.json` | **NEVER MODIFY** | Excel-extracted reference values. |

---

## 4. Database Schema Summary

### Existing tables
`clients, materials, projects, mix_designs, reports, users, audit_log` (latter 2 unused).

### Phase 1–4 additions to `projects` (all nullable, auto-migrated on legacy DBs)
- `modules_json` — `{"mix_design":"complete","structural":"complete",...}`
- `binder_grade` — e.g. `"VG-30"`, `"CRMB"`
- `binder_properties_json` — `{"penetration":65,"softening_point":55,"_notes":"..."}`

### New `structural_designs` table (Phase 4)
`id, project_id, inputs_json, design_msa, growth_factor, subgrade_mr_mpa, total_pavement_thickness_mm, composition_json, notes, computed_at`. Cascade-delete from Project.

### Migration helper
`repository._migrate_schema()` runs on every DB connect. Idempotent `PRAGMA table_info` → `ALTER TABLE ADD COLUMN`. **Add new lines here for every new column in Phase 5+.**

### Legacy quirk
SQLite cannot drop `NOT NULL`. `projects.mix_type` (legacy NOT NULL) is saved as `""` for "not selected". Code reads `if not p.mix_type`.

---

## 5. Dynamic Specification System (Phase 2)

- **Source of truth:** `app/data/mix_specs.json` (bundled).
- **User override:** `%LOCALAPPDATA%\PavementLab\mix_specs.json` (takes precedence if present).
- **Two globals populated at import:**
  - `MIX_SPECS: dict[str, MixSpec]` — only types with a `marshall` block (10 of 25)
  - `MIX_TYPES: dict[str, MixTypeRecord]` — all 25 types with richer metadata
- **Reload at runtime:** `reload_specs()` mutates both dicts in place — existing imports stay valid.
- **Save:** `save_specs({code: rec})` merges into user-override file. Bundled defaults never modified.
- **Status field:** `"verified"` (5 types: DBM-I, DBM-II, BC-I, BC-II, BM) or `"placeholder_editable"` (20 types). **Never invent IRC limits — keep status honest.**
- **Fallback:** if JSON missing/malformed, hardcoded `_FALLBACK_MIX_SPECS` (6 original specs) is used.

---

## 6. Binder Grade System (Phase 3)

- **Source:** `app/data/binder_grades.json` → `BINDER_GRADES: dict[str, BinderGrade]`.
- **10 grades:** VG-10, VG-20, VG-30, VG-40, CRMB, PMB, Emulsion, PME, Foam Bitumen, Custom.
- **Property keys** (canonical, defined in `PROPERTY_LABELS`):
  `specific_gravity, penetration, softening_point, ductility, viscosity, flash_point, elastic_recovery, residue_pct, storage_stability, particle_charge, expansion_ratio, half_life`. **Use these exact keys.**
- **Per-grade `applicable_tests`** controls which properties show in the project-form dialog.
- **Word report** picks up `binder_grade` + `binder_properties` from `ReportContext`. Sec 1 row + Sec 5 SG label + new "Binder Properties" sub-table.

---

## 7. Structural Module Status (Phase 4)

✅ **Done:**
- IRC:37 cumulative MSA (Eq 3.1)
- Subgrade Mr from CBR (Eq 4.1/4.2)
- Catalogue layer suggestion (clearly labeled placeholder)
- DB persist + cascade-delete
- UI: independent (no mix-design required), pre-fills from last save
- Hand-verified math: MSA=35.75 for n=15, r=7.5%, A=2000, D=0.75, F=2.5; Mr(5)=50; Mr(10)=76.83

🟡 **Deferred (do NOT add now):**
- IITPAVE / mechanistic fatigue & rutting → reserved fields `fatigue_check`, `rutting_check` exist in `StructuralResult`
- Word report for structural design → **Phase 6**
- Per-layer modulus editing in UI → Phase 7 polish

---

## 8. Pending Phases

| # | Name | Build |
|---|---|---|
| 5 | Maintenance / Rehabilitation skeleton | New `app/core/maintenance/` package (overlay, cold_mix, micro_surfacing). New `MaintenanceDesign` DB table. New `app/ui/widgets/maintenance_panel.py` with sub-tabs. **Skeleton-only**; no advanced calcs. |
| 6 | Report improvements | Module-aware report builder. Add structural Word report. New `app/reports/report_builder.py` (combined report). **Hide PDF button** in `results_panel.py`. |
| 7 | UI cleanup + Material Quantity Calculator | Back-button polish, module-card status colors, dashboard confirmations. **Add Material Quantity Calculator UI** (engine = simple formulas). |
| 8 | Testing + final QA + EXE rebuild | New tests (structural, maintenance, spec loading). PyInstaller rebuild + zip + shortcut refresh. |

---

## 9. Deferred Features (cross-phase)

- **Material Quantity Calculator UI** — Phase 7.
- **IITPAVE integration** — not committed to any phase.
- **Spec admin: gradation editor + binder-grade editor** — Phase 2 ships Marshall-only edit; full editor = Phase 7.
- **User auth / multi-user** — `users` / `audit_log` tables exist but UNUSED.
- **PDF export** — Phase 6 will hide button. Engine left intact (uses `docx2pdf` / LibreOffice).
- **EXE rebuild** — Phase 8 only. User asked NOT to rebuild after each phase.

---

## 10. Important Warnings

- 🛑 **Never modify** `tests/test_excel_parity.py` or `tests/golden/shirdi_dbm.json`.
- 🛑 **Never refactor** `app/core/*.py` (the 10 engine files) — only ADD new files.
- 🛑 **Never refactor** `app/graphs/marshall_charts.py` or `app/ui/widgets/inputs_panel.py`.
- 🛑 **Never invent** official IRC/MoRTH limits. Mark unknown specs as `"placeholder_editable"`.
- 🛑 **Never rebuild EXE** between phases unless user explicitly asks.
- 🛑 **Never reassign** `MIX_SPECS` or `MIX_TYPES` dicts — mutate in place (`reload_specs()` already does this).
- ⚠ **Legacy DB**: `projects.mix_type` is NOT NULL — save `""` for "not selected", never `None`.
- ⚠ **Back-button lambdas** must use `*_` to swallow Qt's `clicked(bool)` arg.
- ⚠ **Slots dataclasses** (`MixTypeRecord` etc.) have no `__dict__` — use `dataclasses.replace` or `copy.deepcopy`.
- ⚠ **Frozen `ReportContext`** — when extending, only add new fields with defaults.

---

## 11. Safe Continuation Rules

1. Read this file first.
2. Run `python -m pytest tests/test_excel_parity.py -q` — must show `16 passed`.
3. Implement only the requested phase. **Stop after each phase and wait for approval.**
4. Compact additive style:
   - Create new files for new modules.
   - Modify existing files only at the touch-points listed in the phase plan.
5. **New DB column?** Add to `schema.py` AND add `ALTER TABLE` line in `_migrate_schema()`.
6. **New DB table?** `Base.metadata.create_all()` handles creation; add cascade-delete relationship on `Project` if it belongs to a project.
7. **New UI page?** Mirror Phase 4 pattern:
   - Inherit `QWidget`, top-level `PageHeader` from `common.py`.
   - Register `self.<name>` in `MainWindow._build()`.
   - Add key to `SIDEBAR_ITEMS` and to the `widget = {...}` dict.
   - Add to `back_routes` tuple.
   - Add `elif key == "...":` branch in `_on_module_selected`.
   - Emit a `saved` signal; handle in main_window to refresh hub + dashboard.
8. **New module status?** Call `db.set_module_status(pid, "<key>", "complete")` after save.
9. **Module-status keys** (exact strings — `module_hub.py` keys them):
   - `mix_design` ✅ · `structural` ✅ · `maintenance` (Phase 5) · `material_qty` (Phase 7) · `specs_admin` ✅ · `reports` (Phase 6).
10. **Module-status values:** `"empty"` | `"in_progress"` | `"complete"`.
11. **Test recipe per phase:**
    - Run parity tests.
    - Headless smoke (offscreen Qt, silence QMessageBox): create project → exercise new module → check DB roundtrip → cascade delete.
12. **After every phase:** stop, summarize files changed + test result, wait for approval. **Do not chain phases.**

---

## 12. How to Resume from Phase 5

Phase 5 = **Maintenance / Rehabilitation Module Skeleton**.

**Plan (additive, no refactors):**

| Action | File |
|---|---|
| NEW engine package | `app/core/maintenance/__init__.py` |
| NEW — BBD overlay | `app/core/maintenance/overlay.py` (inputs: deflection readings, T-correction, season factor, traffic → characteristic deflection + overlay thickness) |
| NEW — Cold mix | `app/core/maintenance/cold_mix.py` (skeleton: gradation + emulsion → binder content + mix proportion) |
| NEW — Micro surfacing | `app/core/maintenance/micro_surfacing.py` (Type II / III inputs → mix proportion + pass/fail) |
| Export new symbols | `app/core/__init__.py` |
| NEW table | `app/db/schema.py` → `MaintenanceDesign(project_id, sub_module, inputs_json, results_json, notes, computed_at)` + cascade-delete relationship on `Project` |
| Add CRUD | `app/db/repository.py` → `save_maintenance_design()`, `latest_maintenance_design()` |
| NEW UI panel with sub-tabs | `app/ui/widgets/maintenance_panel.py` (sub-tabs: Overlay, Cold Mix, Micro Surfacing; each minimal input + compute + result card + save) |
| Register in router | `app/ui/main_window.py` → import, add to stack, sidebar item `"Maintenance"`, back-route, hub branch `elif key == "maintenance":` |

**Skeleton boundaries (strict):**
- ✅ Compute basic engineered numbers (e.g. characteristic deflection, overlay thickness via simple IRC:81 formula).
- ❌ No advanced mechanistic calc.
- ❌ No Word report (deferred to Phase 6).
- ❌ No EXE rebuild.

**Verification:**
- 16/16 parity still pass.
- Headless smoke: create project (no mix-type) → enter Maintenance → compute Overlay → save → DB roundtrip → cascade delete.

---

## 13. Files / Modules That Must NOT Be Refactored

| Path | Why |
|---|---|
| `app/core/*.py` (the 10 engine files) | Verified to 1e-9 against Excel. Parity tests pin them. |
| `tests/test_excel_parity.py` | Golden safety net. |
| `tests/golden/shirdi_dbm.json` | Excel-extracted reference values. |
| `app/graphs/marshall_charts.py` | Chart appearance matches Excel exactly. |
| `app/ui/widgets/inputs_panel.py` | Demo-data constants and tab structure are stable. |
| `app/ui/widgets/results_panel.py` | UI matches Word report layout. |
| `app/reports/word_report.py` | Only additive changes. |

**Add new files for new functionality. Existing engine files = read-only.**

---

**End of handoff. Resume with `start phase 5` after reading this file.**
