"""Phase 11 — Image Evidence Foundation (foundation step only).

Filesystem-only pipeline for storing pavement-condition photographs alongside
a survey. No DB migration, no UI/report wiring, no ML — those land in later
Phase-11 sub-steps. The public surface is intentionally narrow and pure so
it can be unit-tested and wired in piecemeal.

Storage layout
--------------
    IMAGES_DIR / "condition" / <project_id> / <survey_id> / <sha16>.jpg

* Images are normalized to JPEG quality 85, max-edge 1600 px (Pillow
  ``thumbnail`` preserves aspect ratio).
* The on-disk filename is the first 16 hex chars of the SHA-256 of the
  *output* JPEG bytes; this naturally dedupes re-uploads of the same image.
* Returned paths are POSIX-style and relative to ``IMAGES_DIR`` so they
  remain portable when persisted later (e.g. in a DB column or report
  context).

What this module does NOT do (deliberately deferred):
  * No ``.meta.json`` sidecars — ``list_evidence`` reconstructs evidence
    from disk on a best-effort basis (``original_filename`` and
    ``classification`` are placeholders until structured persistence
    lands).
  * No call into ``Database.delete_project`` — ``delete_project_images``
    is exposed so the DB layer can wire it later.
  * No real classifier — ``classify`` always returns the empty stub.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from PIL import Image

from app.config import IMAGES_DIR
from app.core.code_refs import CodeRef


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_EDGE_PX: int = 1600
JPEG_QUALITY: int = 85
_RELATIVE_ROOT: str = "condition"
_SHA_PREFIX_LEN: int = 16

REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("Phase-11", "",
            "Image evidence — JPEG q85, max-edge 1600 px, SHA-256 naming"),
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ClassificationStub:
    """Placeholder classifier output. No ML in Phase 11 foundation."""
    label: str = "unclassified"
    confidence: float = 0.0
    model_id: str = ""        # empty string ⇒ no model attached


@dataclass(frozen=True, slots=True)
class ImageEvidence:
    """Filesystem-backed evidence attached to a condition survey."""
    relative_path: str        # POSIX, relative to IMAGES_DIR
    project_id: int
    survey_id: int
    original_filename: str
    sha256: str
    width_px: int
    height_px: int
    bytes: int
    classification: ClassificationStub = field(default_factory=ClassificationStub)
    notes: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _survey_dir(project_id: int, survey_id: int) -> Path:
    return IMAGES_DIR / _RELATIVE_ROOT / str(project_id) / str(survey_id)


def _project_dir(project_id: int) -> Path:
    return IMAGES_DIR / _RELATIVE_ROOT / str(project_id)


def _relpath(abs_path: Path) -> str:
    return abs_path.relative_to(IMAGES_DIR).as_posix()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def attach_image(
    project_id: int,
    survey_id: int,
    src_path: str | Path,
    *,
    notes: str = "",
) -> ImageEvidence:
    """Normalize ``src_path`` to JPEG and store it under the survey folder.

    Pillow opens the source (any format it supports), converts to RGB,
    downscales so the longer edge is at most ``MAX_EDGE_PX`` while
    preserving aspect ratio, and writes JPEG at quality ``JPEG_QUALITY``.
    The output filename is derived from the SHA-256 of the JPEG bytes so
    repeated uploads of the same image deduplicate on disk.
    """
    src = Path(src_path)
    dest_dir = _survey_dir(project_id, survey_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as im:
        rgb = im.convert("RGB")
        rgb.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
        width, height = rgb.size
        # Encode to JPEG in-memory first so the on-disk filename can be
        # the SHA-256 of the *encoded* bytes (stable, content-addressed).
        from io import BytesIO
        buf = BytesIO()
        rgb.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        jpeg_bytes = buf.getvalue()

    digest = _sha256_bytes(jpeg_bytes)
    dest = dest_dir / f"{digest[:_SHA_PREFIX_LEN]}.jpg"
    if not dest.exists():
        dest.write_bytes(jpeg_bytes)

    return ImageEvidence(
        relative_path=_relpath(dest),
        project_id=project_id,
        survey_id=survey_id,
        original_filename=src.name,
        sha256=digest,
        width_px=width,
        height_px=height,
        bytes=dest.stat().st_size,
        classification=ClassificationStub(),
        notes=notes,
    )


def list_evidence(project_id: int, survey_id: int) -> Tuple[ImageEvidence, ...]:
    """Enumerate JPEGs under the survey folder.

    Best-effort reconstruction: ``original_filename`` falls back to the
    on-disk filename and ``classification`` is the empty stub because
    Phase 11 foundation does not yet persist sidecar metadata.
    """
    folder = _survey_dir(project_id, survey_id)
    if not folder.is_dir():
        return ()
    out: list[ImageEvidence] = []
    for p in sorted(folder.glob("*.jpg")):
        try:
            with Image.open(p) as im:
                w, h = im.size
        except Exception:
            continue
        data = p.read_bytes()
        digest = _sha256_bytes(data)
        out.append(ImageEvidence(
            relative_path=_relpath(p),
            project_id=project_id,
            survey_id=survey_id,
            original_filename=p.name,
            sha256=digest,
            width_px=w,
            height_px=h,
            bytes=len(data),
            classification=ClassificationStub(),
            notes="",
        ))
    return tuple(out)


def delete_evidence(project_id: int, survey_id: int, relative_path: str) -> bool:
    """Delete a single evidence file. Returns True if a file was removed."""
    target = IMAGES_DIR / Path(relative_path)
    # Guard: must live under the expected survey folder (prevents traversal).
    try:
        target.resolve().relative_to(_survey_dir(project_id, survey_id).resolve())
    except ValueError:
        return False
    if target.is_file():
        target.unlink()
        return True
    return False


def delete_project_images(project_id: int) -> int:
    """Hard-delete the project's image tree. Returns count of files removed.

    Exposed so the DB layer can call this from ``delete_project`` in a
    later Phase-11 step; not wired yet.
    """
    folder = _project_dir(project_id)
    if not folder.is_dir():
        return 0
    count = sum(1 for _ in folder.rglob("*") if _.is_file())
    shutil.rmtree(folder, ignore_errors=True)
    return count


def classify(evidence: ImageEvidence) -> ClassificationStub:
    """Placeholder classifier. Always returns the empty stub.

    Real ML/heuristic classification lands in a later phase. Kept here so
    callers can be written against a stable seam today.
    """
    return ClassificationStub()


__all__ = [
    "MAX_EDGE_PX",
    "JPEG_QUALITY",
    "REFERENCES",
    "ImageEvidence",
    "ClassificationStub",
    "attach_image",
    "list_evidence",
    "delete_evidence",
    "delete_project_images",
    "classify",
]
