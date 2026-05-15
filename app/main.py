"""Application entry point."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app import __app_name__
from app.config import APP_DIR
from app.ui.main_window import MainWindow


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("PavementLab")

    qss_path = APP_DIR / "ui" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
