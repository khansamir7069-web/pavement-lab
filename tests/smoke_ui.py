"""Headless smoke test of the desktop UI.

Constructs MainWindow on the native Qt platform, drives a new-project +
compute flow programmatically, and exits within ~2 seconds. Writes a result
file so we don't depend on stdout buffering.
"""
import sys
import traceback
from pathlib import Path

OUT = Path(__file__).with_name("smoke_ui_result.txt")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

lines: list[str] = []
try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)

    def _drive():
        try:
            w = MainWindow()
            w.show()
            lines.append("MainWindow constructed OK")
            w._on_new_project()
            w.project_form.work_name.setText("Smoke Test")
            w.project_form.client.setText("QA")
            # Phase-9 stabilization (F4): explicit mix_type required.
            _mix_idx = w.project_form.mix_type.findData("DBM-II")
            if _mix_idx >= 0:
                w.project_form.mix_type.setCurrentIndex(_mix_idx)
            w.project_form._on_save()
            lines.append(f"project id: {w._current_project_id}")
            w.inputs.set_mix_type("DBM-II")
            w._on_compute()
            r = w._last_result
            lines.append(f"OBC%: {r.obc.obc_pct:.4f}")
            lines.append(f"Gsb: {r.bulk_sg_blend:.4f}")
            lines.append(f"Compliance: {'PASS' if r.compliance.overall_pass else 'FAIL'}")
            lines.append(f"summary rows: {len(r.summary.rows)}")
            lines.append("SMOKE OK")
        except Exception:
            lines.append("SMOKE FAIL (in driver)")
            lines.append(traceback.format_exc())
        finally:
            OUT.write_text("\n".join(lines), encoding="utf-8")
            QApplication.quit()

    QTimer.singleShot(50, _drive)
    QTimer.singleShot(8000, QApplication.quit)   # hard kill safety
    app.exec()
except Exception:
    lines.append("SMOKE FAIL (boot)")
    lines.append(traceback.format_exc())
    OUT.write_text("\n".join(lines), encoding="utf-8")
