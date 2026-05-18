"""Phase-44 smoke - local installer preparation readiness refinement."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_tmp = Path(tempfile.mkdtemp(prefix="phase44_local_installer_preparation_"))
_db_path = _tmp / "phase44.db"

import app.config as _cfg  # noqa: E402
_cfg.DB_PATH = _db_path

from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QTextEdit  # noqa: E402

from app.core import (  # noqa: E402
    DEPLOYMENT_CHECK_FAIL,
    DEPLOYMENT_CHECK_PASS,
    LOCAL_INSTALLER_PREPARATION_FORMAT,
    build_deployment_packaging_checklist,
    build_local_installer_preparation_checklist,
    format_deployment_checklist_item_text,
    validate_runtime_environment,
)
from app.db.repository import Database  # noqa: E402

import app.db.repository as _repo  # noqa: E402


_dialogs: list[QDialog] = []
QDialog.exec = lambda self, *a, **k: _dialogs.append(self) or 0


_FILES = (
    "run.py",
    "requirements.txt",
    "Launch.bat",
    "Setup.bat",
    "Build.bat",
    "build/installer/pyinstaller.spec",
    "build/installer/bundle_iitpave.md",
    "build/pavement_lab.spec",
    "build/installer.iss",
    "build/build_exe.ps1",
)

_DIRS = (
    "app",
    "app/data",
    "app/external",
    "app/reports/templates",
)


def _complete_repo_tree(root: Path) -> None:
    for rel in _DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    for rel in _FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"phase44 fixture: {rel}\n", encoding="utf-8")


def _runtime_paths(root: Path) -> dict[str, Path]:
    return {
        "reports": root / "reports",
        "exports": root / "exports",
        "logs": root / "logs",
        "diagnostics": root / "diagnostics",
        "temp": root / "tmp",
    }


def _safe_text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def main() -> int:
    print("=== 1) Local installer preparation checklist passes on a complete tree ===")
    complete_root = _tmp / "complete_repo"
    _complete_repo_tree(complete_root)
    complete = build_local_installer_preparation_checklist(repo_root=complete_root)
    assert complete.status == DEPLOYMENT_CHECK_PASS
    assert complete.as_dict()["format"] == LOCAL_INSTALLER_PREPARATION_FORMAT
    assert complete.build_executed is False
    assert complete.installer_created is False
    assert complete.cloud_deployment_enabled is False
    assert complete.online_activation_enabled is False
    assert all(item.readable for item in complete.assets)
    print("  [PASS] complete local packaging inputs are inventoried without running a build")

    print("\n=== 2) Missing required installer assets fail explicitly ===")
    incomplete_root = _tmp / "incomplete_repo"
    (incomplete_root / "app" / "data").mkdir(parents=True)
    incomplete = build_local_installer_preparation_checklist(repo_root=incomplete_root)
    assert incomplete.status == DEPLOYMENT_CHECK_FAIL
    assert incomplete.fail_count >= 1
    assert any(item.key == "entrypoint" and item.failed for item in incomplete.assets)
    incomplete_text = _safe_text(incomplete.as_dict())
    assert "build_executed" in incomplete_text
    assert "installer_created" in incomplete_text
    assert "cloud_deployment_enabled" in incomplete_text
    assert "online_activation_enabled" in incomplete_text
    print("  [PASS] missing source-tree assets are blockers, not silent assumptions")

    print("\n=== 3) Deployment diagnostics can include installer preparation safely ===")
    app_dir = _tmp / "app_runtime"
    app_dir.mkdir()
    runtime_root = _tmp / "runtime_ready"
    diagnostics = validate_runtime_environment(
        app_dir=app_dir,
        user_data_dir=runtime_root,
        runtime_paths=_runtime_paths(runtime_root),
        create_missing=True,
    )
    checklist = build_deployment_packaging_checklist(
        diagnostics=diagnostics,
        include_iitpave_discovery=False,
        include_installer_preparation=True,
        installer_repo_root=complete_root,
    )
    installer_items = [item for item in checklist.items if item.key == "local_installer_preparation"]
    assert len(installer_items) == 1
    assert installer_items[0].status == DEPLOYMENT_CHECK_PASS
    rendered = format_deployment_checklist_item_text(installer_items[0])
    rendered_safe = rendered.lower()
    assert "build_executed" in rendered_safe
    assert "false" in rendered_safe
    assert "activation" in rendered_safe
    print("  [PASS] installer preparation appears as a read-only deployment checklist item")

    print("\n=== 4) Existing deployment diagnostics UI remains read-only ===")
    _repo._singleton = Database(_db_path)
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow  # noqa: E402

    w = MainWindow()
    w.btn_deployment_diagnostics.click()
    assert _dialogs
    dialog = _dialogs[-1]
    selector = dialog.findChild(QListWidget)
    detail = dialog.findChild(QTextEdit)
    assert selector is not None
    assert detail is not None
    assert detail.isReadOnly()
    found_installer = False
    for row in range(selector.count()):
        selector.setCurrentRow(row)
        if "local_installer_preparation" in detail.toPlainText():
            found_installer = True
            break
    assert found_installer
    assert "build_executed" in detail.toPlainText()
    assert "Deployment diagnostics loaded:" in w.statusBar().currentMessage()
    w.close()
    app.processEvents()
    print("  [PASS] UI exposes installer preparation diagnostics without edit actions")

    print("\nPHASE 44 LOCAL INSTALLER PREPARATION SMOKE: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
