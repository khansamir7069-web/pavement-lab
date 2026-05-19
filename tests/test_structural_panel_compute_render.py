from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core import StructuralInput, compute_structural_design
from app.ui.widgets.structural_panel import StructuralPanel


OLD_IITPAVE_PLACEHOLDER = "Placeholder — IITPAVE / mechanistic check not yet integrated"


class _DummyDb:
    def latest_structural_design(self, project_id: int):
        return None


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_structural_compute_does_not_render_legacy_iitpave_placeholder() -> None:
    _app()
    panel = StructuralPanel(_DummyDb())

    panel._on_compute()

    assert panel.last_result() is not None
    assert OLD_IITPAVE_PLACEHOLDER not in panel.lbl_checks.text()
    assert OLD_IITPAVE_PLACEHOLDER not in panel.last_result().fatigue_check
    assert OLD_IITPAVE_PLACEHOLDER not in panel.last_result().rutting_check
    assert (
        "IITPAVE unavailable" in panel.lbl_checks.text()
        or "epsilon_t" in panel.lbl_checks.text()
    )


def test_structural_render_guard_replaces_raw_unrun_mechanistic_status() -> None:
    _app()
    panel = StructuralPanel(_DummyDb())
    raw_result = compute_structural_design(StructuralInput())

    panel._render(raw_result)

    assert OLD_IITPAVE_PLACEHOLDER not in panel.lbl_checks.text()
    assert (
        "IITPAVE unavailable" in panel.lbl_checks.text()
        or "epsilon_t" in panel.lbl_checks.text()
    )
