# Mix-Design Dynamic Audit — Findings (post-Phase 8)

**Date:** 2026-05-15
**Audit type:** read-only review (no code modified)
**Scope:** Verify whether mix-design backend & UI truly switch behaviour by selected mix type/grade, or whether DBM-II Excel template values are reused for every mix.

---

## 1. Summary verdict

| Layer | Mix-aware? | Notes |
|---|---|---|
| Marshall math (gradation, Gmb, Gmm, OBC, stability/flow) | ✅ mix-agnostic, pure-Python, parity-tested | No DBM-II formula leakage |
| Compliance limits (stability / flow / air voids / VMA / VFB / MQ) | ✅ dynamic per `MIX_SPECS[k]` | JSON-backed; reload works |
| Spec source-tagging (Phase 6 `references[]`) | ✅ all 25 mixes + 10 binders tagged | Phase 6 deliverable |
| Charts overlay (VMA/VFB/AV target lines) | ✅ uses selected spec | |
| Gradation envelope shown in inputs panel | ❌ **DBM-II hardcoded** in `DEMO_SPEC_LOW/UP` | Critical — see §3 |
| Sieve set | ❌ **DBM-II 8-sieve set hardcoded** in `SIEVES` | Critical — see §3 |
| Aggregate-bin labels | ❌ **DBM-II Shirdi blend hardcoded** in `AGGS` | Critical — see §3 |
| Demo data (gradation %, blend, Gmb, Gmm specimens) | ❌ all DBM-II Shirdi numbers | UX (user can overwrite) |
| Compaction blows (75 vs 50 for BM) | ❌ stored in spec but never consumed | Engineer not told |
| `status` flag (`verified` vs `placeholder_editable`) | ❌ never surfaced in UI / report | SDBC/SDAC/SMA run silently |
| Target air voids (4 %) | ⚠ flat constant, not from spec | acceptable today (all verified mixes have 3–5 %) |
| `"DBM-II"` fallback magic-string | ❌ 6 hardcoded fallback occurrences | Silent wrong-default |

**Bottom line:** the **engine math is mix-agnostic**, but the **inputs panel and several fallback paths are DBM-II-shaped**. An engineer who opens a BC-II project and clicks Compute without re-entering gradation will produce a report whose **Marshall compliance is BC-II** but whose **gradation envelope is DBM-II** — an internally inconsistent document.

---

## 2. DBM-II hardcoded risk areas

| Risk area | File:line | What it pins to DBM-II |
|---|---|---|
| Sieve set | `app/ui/widgets/inputs_panel.py:46` | `SIEVES = (37.5, 26.5, 19, 13.2, 4.75, 2.36, 0.3, 0.075)` — DBM-II / BC sieves only. BM/DBM-I need 45 mm; SDBC/SDAC need different breakdown. |
| Gradation envelope | `app/ui/widgets/inputs_panel.py:95-96` | `DEMO_SPEC_LOW = (100, 90, 71, 56, 38, 28, 7, 2)` / `DEMO_SPEC_UP = (100, 100, 95, 80, 54, 42, 21, 8)` — DBM-II Shirdi envelope. |
| Aggregate bins | `app/ui/widgets/inputs_panel.py:47` | `AGGS = ("25mm", "20mm", "6mm", "SD", "Cement")` — DBM-II Shirdi blend |
| Demo passing % | `inputs_panel.py` `DEMO_GRADATION_PASS`, `DEMO_BLEND`, `GMB_DEMO_BY_PB`, `GMM_DEMO` | All DBM-II Shirdi sample numbers |
| Target air voids | `app/core/obc.py:10` | `TARGET_AIR_VOIDS_PCT = 4.0` flat — not driven by `MIX_SPECS[k].air_voids_min/max` |
| Compaction blows | `app/core/compliance.py` `MixSpec.compaction_blows_each_face` | Stored (75 / 50) but never read by engine or shown in UI |
| Fallback string #1 | `app/ui/main_window.py:603` | `mix_type = p.mix_type if p else "DBM-II"` |
| Fallback string #2 | `app/ui/main_window.py:674` | `mix_type_key=(p.mix_type if (p and p.mix_type) else "DBM-II")` |
| Fallback string #3 | `app/ui/main_window.py:733-734` | Import-summary dialog defaults to DBM-II |
| Fallback string #4 | `app/reports/report_builder.py:394` | `mix_type_key=(ctx.mix_type_key or "DBM-II")` |
| Fallback string #5 | `app/reports/report_builder.py:423` | `MIX_SPECS.get(ctx.mix_type_key or "DBM-II")` |
| Fallback string #6 | `app/core/import_summary.py:95,105` | Function signature default + docstring example |
| `status` flag unused | `app/core/compliance.py` `MixTypeRecord.status` | Set correctly in JSON but never read by UI/report |

---

## 3. Required minimal fixes

### F1 — Gradation panel must follow selected mix type (CRITICAL)
**Symptom:** Selecting BC-II in the project form leaves the inputs panel showing the DBM-II envelope.
**Fix:** When entering the Mix-Design Inputs page, read `MIX_TYPES[project.mix_type]`'s `sieve_sizes_mm`, `gradation_lower`, `gradation_upper`, `binder_grades`, `trial_pb_min/max` and load them into the panel. Fall back to DEMO only when no mix_type is set.
**Files:** `inputs_panel.py` (add `set_mix_type(code)`), `main_window.py` (call before `_show_page("inputs")`).
**Effort:** ~30 lines, additive.

### F2 — Surface the `status` flag in UI & report (CRITICAL)
**Symptom:** SDBC-I/II, SDAC-I/II, SMA produce PASS/FAIL silently against placeholder Marshall limits with no warning to the engineer.
**Fix:** When `MIX_TYPES[k].status == "placeholder_editable"`, show an orange banner on inputs panel + results header + Word report Section 7: "⚠ Spec limits for {mix} are not IRC-verified. Results are indicative — confirm against the relevant IRC clause before adoption."
**Files:** `inputs_panel.py`, `results_panel.py`, `word_report.py`.
**Effort:** ~20 lines additive across three files.

### F4 — Replace 6 hardcoded `"DBM-II"` fallback strings (CRITICAL)
**Symptom:** Empty `mix_type` silently routes through DBM-II Marshall limits and DBM-II report template.
**Fix:** In compute path (`main_window.py:603`, `:674`), raise an explicit error / show a QMessageBox if `mix_type` is unset (force user back to project form). In import-summary dialog (`:734`), use the first `verified` MIX_SPECS key, not the literal string. In `report_builder.py:394,423`, only fall through to DBM-II if no live mix-design result is being included (defensive only).
**Files:** `main_window.py`, `report_builder.py`, `import_summary.py`.
**Effort:** ~15 lines additive, mostly guard clauses.

### F3, F5, F6 — Polish (defer to Phase 10+)
- F3: Show compaction-blows requirement on inputs banner & Word report row.
- F5: Drive `target_air_voids` from `(air_voids_min + air_voids_max)/2` per mix.
- F6: Filter `project_form` dropdown to `verified` mixes OR tag placeholder ones with `[placeholder]` suffix.

---

## 4. Recommendation — run a Stabilization Phase before Phase 9

Schedule **Phase 9 = "Mix-Design Stabilization"** (F1 + F2 + F4 only). Rationale:
- Phases 4–8 (Structural / Maintenance / Material Quantity / Traffic) are independent of mix-design correctness.
- Phase 9 as originally planned (next feature work) would compound the inconsistency: more module reports cite the mix-design section that may carry the wrong envelope.
- F1 + F2 + F4 are ~65 lines total, additive, parity-test safe.
- After stabilization, the mix-design module becomes truly mix-type-dynamic and the Phase-6 source-tagging actually shows up where it matters (gradation envelope, blows, status warnings).

**Suggested phase order from here:**
1. **Phase 9 (Stabilization):** F1 + F2 + F4. Headless smoke that flips between DBM-II, BC-II, BM, SMA and asserts the panel + report differ.
2. **Phase 10 (whatever was originally planned).**
3. **Phase 11+ polish:** F3, F5, F6 as time permits.

---

## 5. Mixes currently safe vs unsafe to use for Marshall mix design

| Mix code | In `MIX_SPECS`? | `status` | Safe to compute today? |
|---|---|---|---|
| DBM-I  | ✅ | verified | ✅ (gradation envelope OK if user re-enters; otherwise still DBM-II envelope used) |
| DBM-II | ✅ | verified | ✅ — only mix where DEMO defaults match the spec |
| BC-I   | ✅ | verified | ⚠ Marshall limits correct; gradation envelope shown is DBM-II until user overwrites |
| BC-II  | ✅ | verified | ⚠ same as BC-I |
| SDBC-I | ✅ | placeholder_editable | ⚠⚠ both limits *and* envelope unverified — no UI warning |
| SDBC-II| ✅ | placeholder_editable | ⚠⚠ as above |
| SDAC-I | ✅ | placeholder_editable | ⚠⚠ as above |
| SDAC-II| ✅ | placeholder_editable | ⚠⚠ as above |
| BM     | ✅ | verified | ⚠ Marshall limits + 50 blows correct in data; UI still shows DBM-II envelope and doesn't warn about 50-blow specimen prep |
| SMA    | ✅ | placeholder_editable | ⚠⚠ as SDBC |
| MSS / SS / MS / PMC / SC / MA / COLD-MIX / RAP / CRM / FBSM | ❌ (no Marshall block) | placeholder_editable | not selectable in mix-design dropdown — handled separately in maintenance module ✓ |

---

## 6. Honest closing note

The engine math is **clean and mix-agnostic**. The compliance database is **clean and dynamic**. The Phase-6 source-tagging infrastructure is **clean**. The leak is concentrated in **one file** (`inputs_panel.py`) and **six fallback strings** elsewhere. F1 + F2 + F4 will close all three critical gaps with ~65 additive lines.

Until then: **for non-DBM-II mixes, the engineer must manually overwrite the gradation envelope cells in the inputs panel before clicking Compute**, otherwise the report will be internally inconsistent.

---

## 7. Phase 9 Stabilization — closed 2026-05-15

F1 + F2 + F4 are landed. Tracked in `tests/_smoke_phase9_stabilization.py`.

| Fix | What changed | Files |
|---|---|---|
| **F1** dynamic gradation/sieve loading | `InputsPanel.set_mix_type(code)` rebuilds the gradation tab from `MIX_TYPES[code]` — sieve set, lower/upper envelope, mix-name header with applicable-code source tag. Demo defaults remain as the fallback only when no mix type is selected. Wired into `_on_module_selected("mix_design")` and `_on_load_demo`. | `app/ui/widgets/inputs_panel.py`, `app/ui/main_window.py` |
| **F2** placeholder/unverified warnings | Orange banner on the gradation tab, on the results panel above the compliance card, and inserted into the Word report below the title block. Triggered by `MIX_TYPES[code].status == "placeholder_editable"`. Banner text quotes the applicable-code source from `MixTypeRecord`. | `app/ui/widgets/inputs_panel.py`, `app/ui/widgets/results_panel.py`, `app/reports/word_report.py`, `app/ui/main_window.py` |
| **F4** remove hidden DBM-II fallback | Compute path now redirects to project form if `mix_type` is empty (defensive — hub guard runs first). `_build_report_context` no longer rewrites empty mix_type to DBM-II. Import-summary dialog defaults to the first **verified** entry in `MIX_SPECS` instead of the literal `"DBM-II"`. `build_combined_report` raises `ValueError` if a live mix-design result is supplied with empty `mix_type_key`. `parse_summary_excel` requires `mix_type_key` explicitly. | `app/ui/main_window.py`, `app/reports/report_builder.py`, `app/core/import_summary.py` |

**Smoke coverage:** `python -m tests._smoke_phase9_stabilization` asserts (1) DBM-II loads 8 sieves, (2) DBM-I loads 9 sieves including 45 mm, (3) BC-II envelope differs from DBM-II, (4) SMA placeholder banner is visible on inputs and results panels, (5) `parse_summary_excel` rejects empty mix_type_key, (6) `build_combined_report` rejects empty mix_type_key when a live mix-design is included, (7) zero `"DBM-II"` code literals remain in `app/ui/` or `app/reports/`, (8) Marshall compute still passes for DBM-II / BC-II / SMA using the panel pipeline. Existing parity (16/16) and prior phase smokes (Maintenance, Phase 6/7/8, smoke_ui, smoke_export) all stay green.

**Deferred (Phase 10+):** F3 (compaction-blows badge), F5 (target_air_voids driven by spec midpoint), F6 (filter project_form dropdown to verified entries). No `references[]` plumbing changes — Phase 6 source-tags now surface in the gradation tab's mix-name label and inside the placeholder banner.
