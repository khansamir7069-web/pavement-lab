# Checkpoint 3 Validation Report: A-to-J Phase and UI Mapping

This report maps the SamPave engineering phases (A to J) to their respective codebase implementations, UI screens, and test suites.

## 1. UI Screen to Phase Mapping

Below is the mapping of all screens available in the main application layout to the engineering design phases:

| Sidebar Item / Screen Key | UI Panel / Widget Class | Matching Phase(s) | Description |
|---|---|---|---|
| **Dashboard** (`dashboard`) | `Dashboard` | Phase A | Project lists, create/open/delete, import/export JSON. |
| **Project** (`project`) | `ProjectForm` | Phase A | Project meta, client selection, VG-30/CRMB binder grade dialogs. |
| **Module Hub** (`hub`) | `ModuleHub` | Phase A, J | Unified engineering routing tiles and module statuses. |
| **Mix Design Inputs** (`inputs`) | `InputsPanel` | Phase E | Marshall mix gradation tables, specific gravity, Gmb/Gmm. |
| **Traffic / MSA** (`traffic`) | `TrafficPanel` | Phase B | CVPD, growth rate, lane configs, VDF presets lookup. |
| **Structural Design** (`structural`)| `StructuralPanel` | Phase C, D, F, G, I, H | Resilient modulus from CBR, suggested layer compositions, IITPAVE run. |
| **Maintenance** (`maintenance`) | `MaintenancePanel` | Phase J | Sub-tabs: Benkelman Beam Deflection (BBD) Overlay, Cold Mix, Micro. |
| **Material Quantity** (`material_qty`)| `MaterialQuantityPanel` | Phase J | Bill of Quantities (BOQ) list and density/thickness calculations. |
| **Condition Survey** (`condition`) | `ConditionSurveyPanel` | Phase J | Pavement distress severity records and PCI calculations. |
| **Results & Report** (`results`) | `ResultsPanel` | Phase E, J | OBC calculation results, Marshall curve plots, docx/PDF export. |
| **Specifications** (`specs_admin`) | `SpecAdminPanel` | Phase E | Marshall spec criteria administrator overrides. |

---

## 2. Phase-by-Phase Code & Validation Inventory

### Phase A — IRC:37 Foundation
* **Files / Classes / Functions:**
  * `app/ui/widgets/project_form.py`: `ProjectForm` (Project info UI)
  * `app/db/schema.py`: `Project` (SQLAlchemy model)
  * `app/db/repository.py`: CRUD facades (`save_project`, `get_project`)
* **UI Screen Found:** Yes, "Project" panel
* **Test File Found:** Yes, `tests/smoke_ui.py`
* **Status:** **PRESENT**

### Phase B — Traffic / MSA Engine
* **Files / Classes / Functions:**
  * `app/core/traffic.py`: `TrafficInput`, `TrafficResult`, `compute_traffic_analysis`, `vdf_preset`, `ldf_preset`, `traffic_category`
  * `app/ui/widgets/traffic_panel.py`: `TrafficPanel`
* **UI Screen Found:** Yes, "Traffic / MSA" panel
* **Test File Found:** Yes, `tests/_smoke_phase8.py`
* **Status:** **PRESENT**

### Phase C — Subgrade Engine
* **Files / Classes / Functions:**
  * `app/core/structural_design.py`: `compute_subgrade_mr` (Implements $10 \times CBR$ for $CBR \le 5\%$ else $17.6 \times CBR^{0.64}$ resilient modulus conversion)
  * `app/ui/widgets/structural_panel.py`: Subgrade CBR input field
* **UI Screen Found:** Yes, "Structural Design" panel
* **Test File Found:** Yes, `tests/_smoke_phase15_structural_modern.py`, `tests/test_structural_panel_compute_render.py`
* **Status:** **PRESENT**

### Phase D — Pavement Layer Design
* **Files / Classes / Functions:**
  * `app/core/structural_design.py`: `suggest_composition` (suggests thickness layers BC, DBM-II, WMM, GSB based on MSA and subgrade CBR)
  * `app/ui/widgets/structural_panel.py`: Displays composite structure; permits manual thickness overrides
* **UI Screen Found:** Yes, "Structural Design" panel
* **Test File Found:** Yes, `tests/test_structural_panel_compute_render.py`
* **Status:** **PRESENT**

### Phase E — Bituminous + Mix Design
* **Files / Classes / Functions:**
  * `app/core/marshall.py`: `build_marshall_summary`
  * `app/core/obc.py`: `compute_obc`
  * `app/core/compliance.py`: `check_compliance` (parses specs rules)
  * `app/ui/widgets/inputs_panel.py`, `app/ui/widgets/results_panel.py`, `app/ui/widgets/spec_admin.py`
* **UI Screen Found:** Yes, "Mix Design Inputs", "Results & Report", and "Specifications" panels
* **Test File Found:** Yes, `tests/test_excel_parity.py` (16 Excel parity checks), `tests/test_mix_dynamic_material_selection.py`
* **Status:** **PRESENT**

### Phase F — IITPAVE Mechanistic Engine
* **Files / Classes / Functions:**
  * `app/core/iitpave/`: Full input builder (`input_builder.py`), output parser (`parser.py`), runner selections (`runner_config.py`, `runner.py`), and workflow orchestrator (`workflow.py`)
  * `app/core/mechanistic_validation/`: Fatigue calibration (`fatigue.py`) and rutting calibration (`rutting.py`) life equations from IRC:37
* **UI Screen Found:** Yes, "Structural Design" panel triggers the mechanistic workflow and displays results
* **Test File Found:** Yes, `tests/test_iitpave_structural_workflow.py`, `tests/_smoke_phase13_iitpave.py`, `tests/_smoke_phase14_mechanistic_validation.py`
* **Status:** **PRESENT**

### Phase G — NF / NR Acceptance Workflow
* **Files / Classes / Functions:**
  * `app/core/mechanistic_validation/engine.py`: `compute_mechanistic_validation`
  * `app/core/iitpave/workflow.py`: Verdict checks and warning/fail formats
* **UI Screen Found:** Yes, integrated into "Structural Design" panel
* **Test File Found:** Yes, `tests/test_iitpave_structural_workflow.py`
* **Status:** **PRESENT**

### Phase H — Advanced Pavement System (CTB/CTS/Stabilized Layer System)
* **Files / Classes / Functions:**
  * `app/core/iitpave/pavement_structure.py`: Predefines default Poisson's ratio for cement-treated base (`"CTB": 0.25`)
  * *Note:* The design suggest engine does not automatically suggest stabilized layers (cement-treated base/sub-base). However, users can input these layers manually with custom resilient moduli and Poisson's ratios.
* **UI Screen Found:** Yes, integrated into the custom layer input grid of the "Structural Design" panel
* **Test File Found:** Yes, `tests/_smoke_phase9_stabilization.py` (deals with input UI stabilization, not stabilization material calculations)
* **Status:** **PARTIAL** (The structural engine supports elastic analysis for stabilized layers via manual layer inputs; a dedicated automated stabilized catalogue wizard is not present)

### Phase I — IRC Catalogue System
* **Files / Classes / Functions:**
  * `app/core/structural_design.py`: `suggest_composition` contains a hardcoded skeleton catalogue lookup matching design traffic (MSA bands) and subgrade CBR limits to output layer suggestions
* **UI Screen Found:** Yes, integrated into "Structural Design" panel
* **Test File Found:** Yes, `tests/test_structural_panel_compute_render.py`
* **Status:** **PRESENT** (As a design suggestion skeleton per Phase 4 scope)

### Phase J — Final Consultancy Release
* **Files / Classes / Functions:**
  * `app/reports/report_builder.py`: `build_combined_report` (unified Word/DPR generation combining metadata, traffic, survey, rehab, structural, mix calculations, and schema history Selection audits)
  * `app/reports/word_report.py`: `export_to_pdf`
  * `build/pavement_lab.spec`, `Build.bat`: Binary compiler spec
* **UI Screen Found:** Yes, "Results & Report" panel triggers mix-report exports; "Module Hub" triggers the combined DPR report selector dialog
* **Test File Found:** Yes, `tests/smoke_export.py`, `tests/_smoke_phase49_final_release.py`
* **Status:** **PRESENT**

---
**Status of Checkpoint 3:** COMPLETED
