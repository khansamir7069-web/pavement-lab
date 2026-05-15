"""Import a pre-computed Marshall summary table from an Excel file.

Handles the common lab format:

    | <blank> | Bitumen Content % | Aggregate % | Gmm | Gmb | Air Void (%) |
    |         | VMA % | VFB % | Stability (KN) | Flow (mm) | Marshal Quotient |

The header row can be in any row; the function auto-detects it by scanning for
the keyword "Bitumen Content" (case-insensitive).  Columns B-K (indices 1-10)
or A-J (indices 0-9) are accepted.

After parsing, OBC (interpolated at 4 % air voids) and spec compliance are
computed and returned as ``ImportedMixResult``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .compliance import ComplianceResult, MIX_SPECS, check_compliance
from .marshall import MarshallRow, MarshallSummary
from .obc import OBCResult, properties_at_obc


# ---------------------------------------------------------------------------
# Result dataclass (duck-type compatible with MixDesignResult for the UI)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ImportedMixResult:
    """Minimal result produced by importing a summary table.

    Duck-type compatible with ``MixDesignResult`` for the fields used by
    ``ResultsPanel.set_result()`` and ``build_mix_design_docx()``:
      - summary, obc, compliance
      - bulk_sg_blend, bitumen_sg
    Fields not available from a summary-only import are set to None so that
    the word-report builder can skip the corresponding sections.
    """
    summary: MarshallSummary
    obc: OBCResult
    compliance: ComplianceResult
    bulk_sg_blend: float          # Gsb estimated from VMA formula
    bitumen_sg: float = 1.030     # default VG-30 — user can override later

    # These fields don't exist in ImportedMixResult; word_report checks hasattr
    gradation: None = None
    sg_coarse: None = None
    sg_fine: None = None
    gmm: None = None
    gmb: None = None
    stability_flow: None = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _find_header_and_data(rows: list[tuple]) -> tuple[int, int]:
    """Return (header_row_idx, first_col_offset) in the raw row list.

    first_col_offset is 0 if Bitumen Content is in column A, 1 if column B.
    """
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if cell and "bitumen content" in str(cell).lower():
                return i, j  # data rows start at i+1, values start at col j
    raise ValueError(
        "Could not find a 'Bitumen Content %' header in the spreadsheet. "
        "Make sure the file has the standard summary table layout."
    )


def _col(row: tuple, offset: int, idx: int):
    """Safe column fetch; returns None if out of range."""
    pos = offset + idx
    if pos < len(row):
        return row[pos]
    return None


def _float(val) -> float:
    if val is None:
        raise ValueError(f"Missing expected numeric value (got None)")
    return float(val)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_summary_excel(
    path: str | Path,
    mix_type_key: str = "DBM-II",
    gsb: float | None = None,
) -> "ImportedMixResult":
    """Parse *path* (any Excel format) into an :class:`ImportedMixResult`.

    Parameters
    ----------
    path:
        Full path to the .xlsx / .xls / .xlsm file.
    mix_type_key:
        One of ``MIX_SPECS`` keys (``"DBM-I"``, ``"DBM-II"``, ``"BC-I"`` …).
        Used for compliance checking.
    gsb:
        If provided, use this Gsb value directly.  Otherwise estimate it
        from the VMA formula: ``Gsb = Gmb × (100-Pb) / (100 - VMA)``.
    """
    import openpyxl

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb.active

    raw: list[tuple] = [
        tuple(cell.value for cell in row)
        for row in ws.iter_rows()
    ]

    hdr_idx, col_offset = _find_header_and_data(raw)

    # Columns after the Bitumen Content % header (relative positions 0-9):
    # 0: Bitumen Content %
    # 1: Aggregate %
    # 2: Gmm
    # 3: Gmb
    # 4: Air Void (%)
    # 5: VMA %
    # 6: VFB %
    # 7: Stability (KN)
    # 8: Flow (mm)
    # 9: Marshal Quotient

    marshall_rows: list[MarshallRow] = []
    gsb_estimates: list[float] = []

    for row in raw[hdr_idx + 1:]:
        # Skip completely blank rows
        if all(v is None for v in row):
            continue
        pb_val = _col(row, col_offset, 0)
        if pb_val is None:
            continue
        try:
            pb = _float(pb_val)
        except (TypeError, ValueError):
            continue  # skip non-numeric sentinel rows

        ps  = _float(_col(row, col_offset, 1)) if _col(row, col_offset, 1) is not None else 100.0 - pb
        gmm = _float(_col(row, col_offset, 2))
        gmb = _float(_col(row, col_offset, 3))
        av  = _float(_col(row, col_offset, 4))
        vma = _float(_col(row, col_offset, 5))
        vfb = _float(_col(row, col_offset, 6))
        stab= _float(_col(row, col_offset, 7))
        flow= _float(_col(row, col_offset, 8))
        mq  = _float(_col(row, col_offset, 9))

        # Estimate Gsb: VMA = 100 - (Gmb * Ps / Gsb)  =>  Gsb = Gmb*Ps/(100-VMA)
        if gsb is None and vma < 100.0:
            gsb_estimates.append(gmb * ps / (100.0 - vma))

        marshall_rows.append(MarshallRow(
            bitumen_pct=pb,
            aggregate_pct=ps,
            gmm=gmm,
            gmb=gmb,
            air_voids_pct=av,
            vma_pct=vma,
            vfb_pct=vfb,
            stability_kn=stab,
            flow_mm=flow,
            marshall_quotient=mq,
        ))

    if len(marshall_rows) < 3:
        raise ValueError(
            f"Need at least 3 data rows, found {len(marshall_rows)}. "
            "Check that the file has numeric values in the Pb column."
        )

    # Resolve Gsb
    if gsb is None:
        if not gsb_estimates:
            raise ValueError("Cannot estimate Gsb from the data (VMA values invalid).")
        gsb = sum(gsb_estimates) / len(gsb_estimates)

    summary = MarshallSummary(rows=tuple(marshall_rows), gsb=gsb)
    obc = properties_at_obc(summary)

    comp = check_compliance(
        mix_type_key,
        stability_kn=obc.stability_at_obc_kn,
        flow_mm=obc.flow_at_obc_mm,
        air_voids_pct=obc.air_voids_at_obc_pct,
        vma_pct=obc.vma_at_obc_pct,
        vfb_pct=obc.vfb_at_obc_pct,
        marshall_quotient=(
            obc.stability_at_obc_kn / obc.flow_at_obc_mm
            if obc.flow_at_obc_mm else 0.0
        ),
    )

    return ImportedMixResult(
        summary=summary,
        obc=obc,
        compliance=comp,
        bulk_sg_blend=round(gsb, 4),
    )
