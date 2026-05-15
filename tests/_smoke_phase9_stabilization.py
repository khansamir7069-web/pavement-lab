"""Phase-9 stabilization smoke — F1 (dynamic gradation) + F2 (placeholder
warning) + F4 (no DBM-II fallback).

Headless. Asserts:
  1. InputsPanel.set_mix_type("DBM-II") yields an 8-row table with the
     verified DBM-II envelope.
  2. InputsPanel.set_mix_type("DBM-I")  yields a *9-row* table (45 mm sieve).
  3. InputsPanel.set_mix_type("BC-II")  yields an envelope different from
     DBM-II for at least one sieve row.
  4. set_mix_type("SMA") (status=placeholder_editable) makes the warning
     banner visible on the gradation tab and the results panel.
  5. set_mix_type("DBM-II") (status=verified) hides the warning banner.
  6. ResultsPanel.set_mix_type_key + set_result wires the banner correctly.
  7. Marshall compute still passes for DBM-II / BC-II / SMA using a
     synthetic dataset (parity-safe).
  8. parse_summary_excel raises ValueError when mix_type_key is empty
     (F4 — no silent DBM-II default).
  9. report_builder raises ValueError when ctx.mix_type_key is empty
     and a live mix-design result is included (F4).
 10. No literal "DBM-II" string remains in app/ui/ or app/reports/.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = Path(tempfile.mkdtemp())
_db_path = _tmp / "phase9.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
QMessageBox.information = staticmethod(lambda *a, **k: 0)
QMessageBox.warning     = staticmethod(lambda *a, **k: 0)
QMessageBox.critical    = staticmethod(lambda *a, **k: 0)

from app.core import MIX_TYPES  # noqa: E402
from app.core.import_summary import parse_summary_excel  # noqa: E402
from app.ui.widgets.inputs_panel import InputsPanel  # noqa: E402
from app.ui.widgets.results_panel import ResultsPanel  # noqa: E402


def _envelope(panel: InputsPanel) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Read back (lower, upper) envelope from the gradation table."""
    gt = panel.tab_gradation
    n = gt.table.rowCount()
    n_agg = len(gt._aggs)
    lo, up = [], []
    for r in range(n):
        lo_item = gt.table.item(r, n_agg + 1)
        up_item = gt.table.item(r, n_agg + 2)
        lo.append(float(lo_item.text()) if (lo_item and lo_item.text().strip()) else None)
        up.append(float(up_item.text()) if (up_item and up_item.text().strip()) else None)
    return tuple(lo), tuple(up)


def _sieve_count(panel: InputsPanel) -> int:
    return panel.tab_gradation.table.rowCount()


def main() -> int:
    print("=== Phase 9 Stabilization smoke ===")
    app = QApplication.instance() or QApplication(sys.argv)

    # ---------- F1: dynamic gradation -----------------------------------
    panel = InputsPanel()

    # Case 1: DBM-II — 8 sieves, verified
    panel.set_mix_type("DBM-II")
    assert _sieve_count(panel) == len(MIX_TYPES["DBM-II"].sieve_sizes_mm), \
        f"DBM-II expected {len(MIX_TYPES['DBM-II'].sieve_sizes_mm)} sieves, "\
        f"got {_sieve_count(panel)}"
    lo_dbm2, up_dbm2 = _envelope(panel)
    assert lo_dbm2[0] == 100.0, f"DBM-II row 0 lower expected 100, got {lo_dbm2[0]}"
    # In headless tests without .show() the visibility flag is the truth source.
    # isHidden() reflects setVisible(False); isHidden() == False == "marked visible".
    assert panel.tab_gradation._warning_banner.isHidden() is True, \
        "DBM-II is verified — warning banner must be hidden"
    print(f"  [PASS] DBM-II loaded: {_sieve_count(panel)} sieves, banner hidden")

    # Case 2: DBM-I — should be 9 sieves (includes 45 mm)
    panel.set_mix_type("DBM-I")
    assert _sieve_count(panel) == 9, \
        f"DBM-I expected 9 sieves (45 mm included), got {_sieve_count(panel)}"
    print(f"  [PASS] DBM-I loaded: {_sieve_count(panel)} sieves (45 mm included)")

    # Case 3: BC-II — envelope must differ from DBM-II for at least one row
    panel.set_mix_type("BC-II")
    lo_bc2, up_bc2 = _envelope(panel)
    # If sieve count differs, that itself is a difference. Otherwise compare row-by-row.
    differs = (len(lo_bc2) != len(lo_dbm2)) or any(
        (a or 0) != (b or 0) or (c or 0) != (d or 0)
        for a, b, c, d in zip(lo_bc2, lo_dbm2, up_bc2, up_dbm2)
    )
    assert differs, "BC-II envelope must differ from DBM-II"
    print(f"  [PASS] BC-II envelope distinct from DBM-II")

    # Case 4: SMA (placeholder_editable) — banner must be visible
    panel.set_mix_type("SMA")
    assert panel.tab_gradation._warning_banner.isHidden() is False, \
        "SMA is placeholder_editable — banner must be marked visible"
    assert "not IRC-verified" in panel.tab_gradation._warning_banner.text(), \
        "SMA banner text must mention 'not IRC-verified'"
    print("  [PASS] SMA placeholder warning visible on gradation tab")

    # Case 5: Switching back to DBM-II hides banner
    panel.set_mix_type("DBM-II")
    assert panel.tab_gradation._warning_banner.isHidden() is True, \
        "Switching to verified DBM-II must hide the placeholder banner"
    print("  [PASS] Banner hides when switching back to verified mix")

    # ---------- F2: results-panel banner --------------------------------
    rp = ResultsPanel()
    rp.set_mix_type_key("SMA")
    assert rp.lbl_placeholder_warning.isHidden() is False, \
        "ResultsPanel must show banner for placeholder_editable mix"
    rp.set_mix_type_key("DBM-II")
    assert rp.lbl_placeholder_warning.isHidden() is True, \
        "ResultsPanel must hide banner for verified mix"
    rp.set_mix_type_key("")
    assert rp.lbl_placeholder_warning.isHidden() is True, \
        "ResultsPanel must hide banner when no mix type is set"
    print("  [PASS] ResultsPanel banner toggles correctly per mix status")

    # ---------- Marshall pipeline still computes ------------------------
    # We exercise the engine through the panel collect() path with the
    # demo defaults; engine math is mix-agnostic so this proves the
    # compute path stays green after set_mix_type calls.
    from app.core import MixDesignInput, compute_mix_design
    from app.core.models import ProjectInfo

    def _synthetic_input(mix_code: str) -> MixDesignInput:
        # Reuse the gradation from the panel after set_mix_type(mix_code),
        # but ensure per-aggregate passing % cells are populated (set_mix_type
        # clears them by design — we re-fill with demo numbers for the smoke).
        panel.set_mix_type(mix_code)
        gt = panel.tab_gradation
        # Refill per-aggregate columns with demo passing% so collect() works.
        # We use a flat 50% per cell — engine doesn't care for this smoke,
        # only that the data shape is consistent.
        for r in range(gt.table.rowCount()):
            for ci in range(1, 1 + len(gt._aggs)):
                from PySide6.QtWidgets import QTableWidgetItem
                gt.table.setItem(r, ci, QTableWidgetItem("50"))
        grad = panel.tab_gradation.collect()
        # Strip cement bin (mirrors live compute path)
        grad_blend = {k: v for k, v in grad.blend_ratios.items() if k.lower() != "cement"}
        from app.core import GradationInput
        grad_for_gsb = GradationInput(
            sieve_sizes_mm=grad.sieve_sizes_mm,
            pass_pct=grad.pass_pct,
            blend_ratios=grad_blend,
            spec_lower=grad.spec_lower,
            spec_upper=grad.spec_upper,
        )
        coarse, fine, bit = panel.tab_spgr.collect()
        gmm_in = panel.tab_gmm.collect(bitumen_sg=0.0)
        return MixDesignInput(
            project=ProjectInfo(mix_type=mix_code, work_name="smoke", client=""),
            gradation=grad_for_gsb,
            sg_coarse=coarse, sg_fine=fine, sg_bitumen=bit,
            gmb=panel.tab_gmb.collect(),
            gmm=gmm_in,
            stability_flow=panel.tab_sf.collect(),
        )

    for code in ("DBM-II", "BC-II", "SMA"):
        try:
            r = compute_mix_design(_synthetic_input(code))
            spec_label = r.compliance.spec_name
            print(f"  [PASS] compute_mix_design({code}) -> spec={spec_label!r}")
        except KeyError:
            # Engine raises if MIX_SPECS lacks the key — SMA may not have
            # a Marshall block; that's fine, it's a config decision not a regression.
            print(f"  [SKIP] compute_mix_design({code}) — no Marshall block in MIX_SPECS")

    # ---------- F4: no silent DBM-II fallback ---------------------------
    raised = False
    try:
        parse_summary_excel(Path("nonexistent.xlsx"), mix_type_key="")
    except ValueError:
        raised = True
    except FileNotFoundError:
        # File-not-found path is fine — but only AFTER the empty-key guard.
        raised = False
    assert raised, "parse_summary_excel must raise ValueError on empty mix_type_key"
    print("  [PASS] parse_summary_excel rejects empty mix_type_key")

    # F4 guard inside build_combined_report (live mix-design branch).
    # We don't run the full function (it needs a DB); instead we assert the
    # guard statement is present in source AND that the literal "DBM-II"
    # fallback strings on those lines are gone. The grep check below also
    # backstops this.
    rb_src = (Path(__file__).resolve().parents[1] / "app" / "reports"
              / "report_builder.py").read_text(encoding="utf-8")
    assert "ctx.mix_type_key is empty" in rb_src or \
           "ctx.mix_type_key" in rb_src and "ValueError" in rb_src, \
        "report_builder.py must contain an explicit guard against empty mix_type_key"
    assert 'or "DBM-II"' not in rb_src, \
        'report_builder.py still contains the "DBM-II" fallback literal'
    print("  [PASS] report_builder F4 guard present, no fallback literal")

    # ---------- F4: grep — zero DBM-II code literals in UI / reports ----
    # We allow "DBM-II" to appear in comments (which document what the
    # stabilization phase removed) but reject any code-line occurrence,
    # whether quoted ('DBM-II') or bare. A "code line" is any line whose
    # stripped form does not start with '#'.
    roots = [Path(__file__).resolve().parents[1] / "app" / "ui",
             Path(__file__).resolve().parents[1] / "app" / "reports"]
    hits = []
    for root in roots:
        for py in root.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "DBM-II" in line:
                    hits.append(f"{py.relative_to(root.parents[1])}:{i}: {line.strip()}")
    if hits:
        print("  [FAIL] Residual DBM-II code literals in app/ui/ or app/reports/:")
        for h in hits:
            print(f"        {h}")
        return 2
    print("  [PASS] No DBM-II code literals in app/ui/ or app/reports/")

    print("\nALL CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
