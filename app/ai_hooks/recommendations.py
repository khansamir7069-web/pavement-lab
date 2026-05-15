"""AI-readiness stubs.

The UI may call these from the Results panel to display "suggestions" and
"anomaly warnings". The default implementations are deterministic rules; swap
in an LLM or numerical optimiser later without touching anything else.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core import MixDesignResult


@dataclass(frozen=True, slots=True)
class Recommendation:
    title: str
    detail: str
    confidence: float


@dataclass(frozen=True, slots=True)
class Warning:
    severity: str    # "info" | "warn" | "error"
    title: str
    detail: str


def suggest_obc_optimisation(result: MixDesignResult) -> list[Recommendation]:
    """Suggest tweaks to bring failing parameters back into spec."""
    out: list[Recommendation] = []
    for item in result.compliance.items:
        if item.pass_:
            continue
        if item.name.startswith("Air Voids") and item.value < 3:
            out.append(Recommendation(
                title="Reduce bitumen content",
                detail="Air voids below 3 % — consider trialling a lower OBC; "
                       "reducing Pb by 0.3 % will typically lift VIM by ~1 %.",
                confidence=0.6,
            ))
        elif item.name.startswith("Air Voids") and item.value > 5:
            out.append(Recommendation(
                title="Increase bitumen content",
                detail="Air voids above 5 % — consider a higher OBC or finer "
                       "gradation to reduce voids.",
                confidence=0.6,
            ))
        elif item.name == "VMA (%)":
            out.append(Recommendation(
                title="Adjust aggregate gradation",
                detail="Low VMA — increase coarse-aggregate fraction or reduce "
                       "filler content to open the matrix.",
                confidence=0.5,
            ))
        elif item.name == "Stability (kN)":
            out.append(Recommendation(
                title="Check compaction & gradation",
                detail="Low stability — verify compaction temperature, blow "
                       "count, and harder-aggregate substitution.",
                confidence=0.45,
            ))
    return out


def detect_anomalies(result: MixDesignResult) -> list[Warning]:
    """Flag suspicious patterns in raw data and results."""
    warnings: list[Warning] = []

    # Gmb 95% CI failures
    for grp in result.gmb.groups:
        if grp.acceptance != "PASS":
            warnings.append(Warning(
                severity="warn",
                title=f"Gmb dispersion at Pb = {grp.bitumen_pct:.1f}%",
                detail=f"3 specimens did not fit within ±1.96σ; "
                       f"mean={grp.mean:.3f}, σ={grp.stdev_sample:.4f}. "
                       "Consider running additional samples.",
            ))

    # Height-check failures
    for grp in result.stability_flow.groups:
        bad = [s for s in grp.specimens if not s.height_ok]
        if bad:
            warnings.append(Warning(
                severity="info",
                title=f"Marshall specimen height out of range at Pb = {grp.bitumen_pct:.1f}%",
                detail=f"{len(bad)} of {len(grp.specimens)} specimens outside 61.5–65.5 mm. "
                       "Use the include checkboxes to exclude them from averaging.",
            ))

    # OBC outside design range
    pbs = list(result.summary.pbs)
    if result.obc.obc_pct < pbs[0] or result.obc.obc_pct > pbs[-1]:
        warnings.append(Warning(
            severity="warn",
            title="OBC outside tested bitumen range",
            detail=f"OBC = {result.obc.obc_pct:.2f}% lies outside the trial range "
                   f"{pbs[0]}–{pbs[-1]}%. Run additional trials to bracket it.",
        ))

    return warnings
