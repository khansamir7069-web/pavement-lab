"""Smoke-test full pipeline including Word report generation through the UI."""
import sys
import traceback
from pathlib import Path

OUT = Path(__file__).with_name("smoke_export_result.txt")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

lines: list[str] = []
try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    from app.reports import build_mix_design_docx, ReportContext
    from app.graphs import build_chart_set

    app = QApplication(sys.argv)

    def _drive():
        try:
            w = MainWindow()
            w._on_new_project()
            w.project_form.work_name.setText("Shirdi Airport DBM Trial")
            w.project_form.client.setText("Shri Sai Construction")
            w.project_form.agency.setText("Arcstone Infrastructure")
            # Phase-9 stabilization (F4): mix_type is required; pre-select
            # DBM-II to keep this driver's Shirdi DBM dataset coherent.
            _mix_idx = w.project_form.mix_type.findData("DBM-II")
            if _mix_idx >= 0:
                w.project_form.mix_type.setCurrentIndex(_mix_idx)
            w.project_form._on_save()
            # The hub route applies set_mix_type to the inputs panel; we
            # also call it here so the panel's gradation envelope tracks
            # the project's mix type before _on_compute reads it.
            w.inputs.set_mix_type("DBM-II")
            w._on_compute()

            # Build report directly (skipping the file-save dialog)
            ctx = w._build_report_context()
            out_path = Path("build/smoke_report.docx").resolve()
            built = build_mix_design_docx(
                out_path, ctx, w._last_result, w._last_chart_set,
                material_calc=w._last_material_calc,
            )
            lines.append(f"Report built: {built}")
            lines.append(f"Size: {built.stat().st_size} bytes")
            # Confirm Section 8 (Material Calc) made it into the docx
            from docx import Document
            doc = Document(str(built))
            paras = [p.text for p in doc.paragraphs]
            has_material = any("Material Calculation" in t for t in paras)
            lines.append(f"Has Material Calculation section: {has_material}")
            lines.append(f"Material standard wt: {w._last_material_calc.standard.total_mix_weight_g:.2f} g")
            lines.append(f"Material target  wt: {w._last_material_calc.target.total_mix_weight_g:.2f} g")
            assert has_material, "Material section missing from docx"
            lines.append("EXPORT OK")
        except Exception:
            lines.append("EXPORT FAIL")
            lines.append(traceback.format_exc())
        finally:
            OUT.write_text("\n".join(lines), encoding="utf-8")
            QApplication.quit()

    QTimer.singleShot(50, _drive)
    QTimer.singleShot(15000, QApplication.quit)
    app.exec()
except Exception:
    lines.append("BOOT FAIL")
    lines.append(traceback.format_exc())
    OUT.write_text("\n".join(lines), encoding="utf-8")
