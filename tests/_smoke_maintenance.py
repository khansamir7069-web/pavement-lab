"""Phase-5 headless smoke: project -> Maintenance -> compute & save (all 3 subs)
   -> roundtrip read -> cascade delete.

Run with:
    python -m tests._smoke_maintenance
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Use a throwaway DB to keep the user's data safe.
_tmp_db = Path(tempfile.mkdtemp()) / "phase5_smoke.db"

# Patch config BEFORE any app import touches it.
import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _tmp_db

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# Silence QMessageBox by short-circuiting its show methods.
QMessageBox.information = staticmethod(lambda *a, **k: 0)
QMessageBox.warning     = staticmethod(lambda *a, **k: 0)
QMessageBox.critical    = staticmethod(lambda *a, **k: 0)

from app.db.repository import Database  # noqa: E402
from app.ui.widgets.maintenance_panel import MaintenancePanel  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    db = Database(_tmp_db)
    proj = db.create_project(work_name="Phase 5 Smoke")
    pid = proj.id
    print(f"[ok] created project id={pid}")

    panel = MaintenancePanel(db)
    panel.set_project(pid, proj.work_name)

    # --- Overlay ---
    panel.overlay_tab.readings.setText("0.85, 1.05, 0.95, 1.20, 1.10")
    panel.overlay_tab.pav_temp.setValue(28.0)
    panel.overlay_tab.bc_thick.setValue(100.0)
    panel.overlay_tab.msa.setValue(20.0)
    panel.overlay_tab._on_compute()
    r1 = panel.overlay_tab.last_result()
    assert r1 is not None, "overlay compute did not produce a result"
    print(f"[ok] overlay: Dc={r1.characteristic_deflection_mm:.3f} mm  "
          f"h={r1.overlay_thickness_mm:.0f} mm")
    panel.overlay_tab._on_save()

    # --- Cold mix ---
    panel.cold_tab._on_compute()
    r2 = panel.cold_tab.last_result()
    assert r2 is not None
    print(f"[ok] cold mix: residual binder={r2.residual_binder_pct:.2f} %  "
          f"pass={r2.pass_check}")
    panel.cold_tab._on_save()

    # --- Micro surfacing ---
    panel.micro_tab._on_compute()
    r3 = panel.micro_tab.last_result()
    assert r3 is not None
    print(f"[ok] micro: residual binder={r3.residual_binder_pct:.2f} %  "
          f"pass={r3.pass_check}")
    panel.micro_tab._on_save()

    # --- DB roundtrip ---
    for sub in ("overlay", "cold_mix", "micro_surfacing"):
        row = db.latest_maintenance_design(pid, sub)
        assert row is not None, f"no row for {sub}"
        # Inputs JSON must round-trip
        json.loads(row.inputs_json)
        json.loads(row.results_json)
        print(f"[ok] DB row for {sub}: id={row.id}")

    status = db.get_module_status(pid)
    assert status.get("maintenance") == "complete", status
    print(f"[ok] module status: maintenance={status['maintenance']}")

    # --- Cascade-delete project ---
    ok = db.delete_project(pid)
    assert ok, "delete_project failed"
    for sub in ("overlay", "cold_mix", "micro_surfacing"):
        row = db.latest_maintenance_design(pid, sub)
        assert row is None, f"cascade did not delete {sub}: {row}"
    print("[ok] cascade-delete cleared all maintenance rows")

    # --- Independent: panel re-usable on a fresh project ---
    proj2 = db.create_project(work_name="Phase 5 Smoke 2")
    panel.set_project(proj2.id, proj2.work_name)  # pre-fill should silently do nothing
    print(f"[ok] panel re-bound to fresh project id={proj2.id}")
    db.delete_project(proj2.id)

    print("\nPHASE 5 SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
