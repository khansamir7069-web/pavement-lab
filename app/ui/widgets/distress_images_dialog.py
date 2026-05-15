"""Per-distress image attachment dialog — Phase 11 step 3.

A small modal used by the distress-table 'Images' column. Mirrors the
survey-wide gallery on ``ConditionSurveyPanel``: a QListWidget of
attached images plus Add / Remove buttons backed by
``app.core.condition_survey.image_pipeline``.

All attachments share the same per-project draft pool used by the
survey-wide gallery (``IMAGES_DIR / "condition" / <project_id> / 0 /``)
so an image can deduplicate cleanly if it ends up referenced both by a
specific distress and the survey as a whole.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.config import IMAGES_DIR
from app.core.condition_survey.image_pipeline import (
    attach_image,
    delete_evidence,
)


# Same sentinel sub-folder as ConditionSurveyPanel — both UI surfaces
# attach to the per-project draft pool.
DRAFT_SURVEY_ID: int = 0


def _row_label(rel_path: str) -> str:
    abs_path = IMAGES_DIR / Path(rel_path)
    if not abs_path.is_file():
        return f"{rel_path}  (missing)"
    try:
        size_kb = abs_path.stat().st_size / 1024.0
        return f"{abs_path.name}  -  {size_kb:.1f} KB"
    except OSError:
        return rel_path


class DistressImagesDialog(QDialog):
    """Edit the ``image_paths`` tuple attached to one DistressRecord."""

    def __init__(self, project_id: int, distress_label: str,
                 initial_paths: list[str] | tuple[str, ...] = (),
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Images — {distress_label}")
        self.setModal(True)
        self.resize(560, 360)
        self._project_id = project_id
        self._paths: list[str] = list(initial_paths or ())

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<b>Per-distress image evidence</b>  "
            "<span style='color:#6a7180; font-size:9pt;'>"
            "(JPEG q85 / 1600 px max edge; stored under IMAGES_DIR)"
            "</span>"
        ))

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add image...")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove = QPushButton("Remove selected")
        self.btn_remove.clicked.connect(self._on_remove)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.lst = QListWidget()
        lay.addWidget(self.lst, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self.btn_close = QPushButton("Done")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)
        lay.addLayout(close_row)

        self._rebuild_list()

    # ---- helpers ---------------------------------------------------------
    def _rebuild_list(self) -> None:
        self.lst.clear()
        for rel in self._paths:
            item = QListWidgetItem(_row_label(rel))
            item.setData(Qt.UserRole, rel)
            self.lst.addItem(item)

    # ---- handlers --------------------------------------------------------
    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach pavement image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not paths:
            return
        for p in paths:
            try:
                ev = attach_image(self._project_id, DRAFT_SURVEY_ID, p)
            except Exception as e:
                QMessageBox.warning(self, "Image rejected",
                    f"Could not attach {p}:\n{e}")
                continue
            if ev.relative_path not in self._paths:
                self._paths.append(ev.relative_path)
        self._rebuild_list()

    def _on_remove(self) -> None:
        item = self.lst.currentItem()
        if item is None:
            return
        rel = item.data(Qt.UserRole)
        if not rel:
            return
        # Best-effort filesystem delete. The image may still be
        # referenced by the survey-wide gallery or another distress —
        # if so the file is removed but the other row will flag it as
        # "(missing)" until the user clears that reference too. Phase
        # 11 step 3 does not yet track cross-references.
        try:
            delete_evidence(self._project_id, DRAFT_SURVEY_ID, rel)
        except Exception:
            pass
        if rel in self._paths:
            self._paths.remove(rel)
        self._rebuild_list()

    # ---- result ----------------------------------------------------------
    def image_paths(self) -> tuple[str, ...]:
        return tuple(self._paths)
