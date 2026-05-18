"""Application entry point."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import __app_name__, __product_name__
from app.config import APP_DIR
from app.core import startup_deployment_diagnostics
from app.ui.main_window import MainWindow


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def main() -> int:
    configure_logging()
    diagnostics = startup_deployment_diagnostics()
    if not diagnostics.ok or diagnostics.has_warnings:
        log = logging.getLogger(__name__)
        for issue in diagnostics.issues:
            if issue.blocks_runtime:
                log.error("Deployment startup diagnostic: %s", issue.as_dict())
            else:
                log.warning("Deployment startup diagnostic: %s", issue.as_dict())
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__product_name__)

    qss_path = APP_DIR / "ui" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
