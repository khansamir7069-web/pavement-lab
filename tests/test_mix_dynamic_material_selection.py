from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from docx import Document
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from app.core import compute_material_calc, compute_mix_design
from app.core.models import MixDesignInput, ProjectInfo
from app.graphs import build_chart_set
from app.reports.word_report import ReportContext, build_mix_design_docx
from app.ui.widgets.inputs_panel import GradationTab, InputsPanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _set_blend(tab: GradationTab, values: dict[str, float]) -> None:
    for name, spin in tab.blend_spins.items():
        spin.setValue(values.get(name, 0.0))


def _fill_gradation(tab: GradationTab, name: str, value: float = 50.0) -> None:
    ci = tab._available_aggs.index(name) + 1
    for row in range(tab.table.rowCount()):
        tab.table.setItem(row, ci, QTableWidgetItem(f"{value:g}"))


def _fill_10mm_sg(panel: InputsPanel) -> None:
    for row, value in enumerate((3648, 2363, 2005, 1952)):
        panel.tab_spgr.coarse_10.setItem(row, 0, QTableWidgetItem(str(value)))


def _docx_text(path) -> str:
    doc = Document(str(path))
    parts: list[str] = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def test_gradation_active_materials_hide_inactive_blend_inputs() -> None:
    _app()
    tab = GradationTab()

    assert tab.material_group.title() == "Active material selection"
    assert tab.material_group.isHidden() is False
    assert tab.active_checks["10mm"].text() == "10 mm"
    assert tab.active_checks["SD"].text() == "Stone Dust"
    assert "Active: 25 mm, 20 mm, 6 mm, Stone Dust, Cement" in tab._active_summary.text()
    assert tab.active_materials() == ("25mm", "20mm", "6mm", "SD", "Cement")
    assert tab.blend_spins["10mm"].isHidden()
    assert tab.table.isColumnHidden(tab._available_aggs.index("10mm") + 1)

    active = ("25mm", "10mm", "6mm", "SD")
    tab.set_active_materials(active)
    _set_blend(tab, {"25mm": 0.30, "10mm": 0.25, "6mm": 0.20, "SD": 0.25})
    _fill_gradation(tab, "10mm")

    grad = tab.collect()

    assert tuple(grad.blend_ratios) == active
    assert tuple(grad.pass_pct) == active
    assert "20mm" not in grad.blend_ratios
    assert "Cement" not in grad.blend_ratios
    assert tab.active_checks["10mm"].isChecked()
    assert "10 mm" in tab._active_summary.text()
    assert "20 mm" not in tab._active_summary.text()
    assert "Cement" not in tab._active_summary.text()
    assert tab.blend_spins["20mm"].isHidden()
    assert tab.blend_spins["Cement"].isHidden()
    assert tab.table.isColumnHidden(tab._available_aggs.index("20mm") + 1)
    assert tab.table.isColumnHidden(tab._available_aggs.index("Cement") + 1)


def test_active_10mm_requires_user_gradation_data() -> None:
    _app()
    tab = GradationTab()
    tab.set_active_materials(("25mm", "10mm"))
    _set_blend(tab, {"25mm": 0.50, "10mm": 0.50})

    try:
        tab.collect()
    except ValueError as exc:
        assert "Missing gradation data for active material 10mm" in str(exc)
    else:
        raise AssertionError("active 10mm without gradation data should be rejected")


def test_inputs_compute_and_report_use_only_active_materials(tmp_path) -> None:
    _app()
    panel = InputsPanel()
    active = ("25mm", "10mm", "6mm", "Cement")
    panel.tab_gradation.set_active_materials(active)
    _set_blend(
        panel.tab_gradation,
        {"25mm": 0.35, "10mm": 0.25, "6mm": 0.20, "Cement": 0.20},
    )
    _fill_gradation(panel.tab_gradation, "10mm")
    _fill_10mm_sg(panel)

    payload = panel.collect_all()
    grad = payload["gradation"]
    coarse, fine, bit = payload["spgr"]

    assert tuple(grad.blend_ratios) == active
    assert set(coarse) == {"25mm", "10mm"}
    assert set(fine) == {"6mm"}
    assert tuple(payload["material_calc"].blend_ratios) == active

    result = compute_mix_design(
        MixDesignInput(
            project=ProjectInfo(mix_type="DBM-II", materials={name: "" for name in active}),
            gradation=grad,
            sg_coarse=coarse,
            sg_fine=fine,
            sg_bitumen=bit,
            gmb=payload["gmb"],
            gmm=payload["gmm_tab"].collect(bitumen_sg=0.0),
            stability_flow=payload["stability_flow"],
        )
    )
    material_calc = compute_material_calc(payload["material_calc"])

    assert tuple(result.gradation.blend_ratios) == active
    assert tuple(row.name for row in material_calc.dry_material_standard) == active

    report_path = tmp_path / "dynamic_materials.docx"
    build_mix_design_docx(
        report_path,
        ReportContext(
            project_title="Dynamic materials",
            mix_type_key="DBM-II",
            materials={name: "" for name in active},
        ),
        result,
        build_chart_set(result.summary, result.obc),
        material_calc=material_calc,
    )
    text = _docx_text(report_path)

    assert "10mm" in text
    assert "20mm" not in text
    assert "SD" not in text
    assert "Cement" in text
