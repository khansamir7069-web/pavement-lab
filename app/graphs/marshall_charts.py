"""6 Marshall design charts.

Each chart: smooth curve through 5 (Pb, y) points + red diamond at OBC with
data label + red dashed vertical line at OBC. Matches the VBA Module67 chart
style.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.core.interpolation import bracket_interpolate
from app.core.marshall import MarshallSummary
from app.core.obc import OBCResult


@dataclass(frozen=True, slots=True)
class ChartDef:
    key: str
    title: str
    y_label: str
    y_values: tuple[float, ...]
    y_at_obc: float


@dataclass(frozen=True, slots=True)
class MarshallChartSet:
    pbs: tuple[float, ...]
    obc: float
    charts: tuple[ChartDef, ...]


def build_chart_set(summary: MarshallSummary, obc: OBCResult) -> MarshallChartSet:
    pbs = summary.pbs
    defs = (
        ChartDef("air_voids", "Bitumen Content vs Air Voids",
                 "Air Voids (%)",
                 tuple(r.air_voids_pct for r in summary.rows),
                 obc.air_voids_at_obc_pct),
        ChartDef("vma", "Bitumen Content vs VMA",
                 "VMA (%)",
                 tuple(r.vma_pct for r in summary.rows),
                 obc.vma_at_obc_pct),
        ChartDef("vfb", "Bitumen Content vs VFB",
                 "VFB (%)",
                 tuple(r.vfb_pct for r in summary.rows),
                 obc.vfb_at_obc_pct),
        ChartDef("stability", "Bitumen Content vs Marshall Stability",
                 "Stability (kN)",
                 tuple(r.stability_kn for r in summary.rows),
                 obc.stability_at_obc_kn),
        ChartDef("flow", "Bitumen Content vs Flow",
                 "Flow (mm)",
                 tuple(r.flow_mm for r in summary.rows),
                 obc.flow_at_obc_mm),
        ChartDef("gmb", "Bitumen Content vs Gmb",
                 "Gmb",
                 tuple(r.gmb for r in summary.rows),
                 obc.gmb_at_obc),
    )
    return MarshallChartSet(pbs=pbs, obc=obc.obc_pct, charts=defs)


def render_chart_to_axes(ax, cs: MarshallChartSet, cd: ChartDef) -> None:
    xs = np.array(cs.pbs, dtype=float)
    ys = np.array(cd.y_values, dtype=float)

    # Smooth curve through the 5 points using cubic spline for visualization
    from scipy.interpolate import CubicSpline  # noqa: import here for optional dep

    try:
        # Use matplotlib's built-in interpolation via PCHIP for monotonic smoothness
        from scipy.interpolate import PchipInterpolator
        smooth_x = np.linspace(xs.min(), xs.max(), 100)
        smooth_y = PchipInterpolator(xs, ys)(smooth_x)
        ax.plot(smooth_x, smooth_y, "-", color="#2c5d99", linewidth=2, label="Test Results")
    except Exception:
        ax.plot(xs, ys, "-", color="#2c5d99", linewidth=2, label="Test Results")

    ax.plot(xs, ys, "o", color="#2c5d99", markersize=7, markerfacecolor="white", markeredgewidth=1.5)

    # OBC marker + label
    ax.plot([cs.obc], [cd.y_at_obc], "D", color="red", markersize=11,
            markerfacecolor="white", markeredgewidth=1.8, label="At OBC")
    ax.annotate(
        f"{cd.y_at_obc:.2f}",
        xy=(cs.obc, cd.y_at_obc),
        xytext=(5, 10),
        textcoords="offset points",
        fontsize=9, fontweight="bold", color="red",
    )

    # Vertical OBC line
    ax.axvline(cs.obc, color="red", linestyle="--", linewidth=1.3, alpha=0.8)

    ax.set_title(cd.title, fontsize=11, fontweight="bold")
    ax.set_xlabel("Bitumen Content (%)", fontsize=9)
    ax.set_ylabel(cd.y_label, fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.tick_params(labelsize=8)


def save_chart_pngs(cs: MarshallChartSet, out_dir: Path, dpi: int = 150) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for cd in cs.charts:
        fig, ax = plt.subplots(figsize=(5.2, 3.2), dpi=dpi)
        render_chart_to_axes(ax, cs, cd)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        p = out_dir / f"chart_{cd.key}.png"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        paths[cd.key] = p
    return paths
