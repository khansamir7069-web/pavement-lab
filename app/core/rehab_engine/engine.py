"""Phase-12 rehab synthesis engine.

Consumes the survey-level outputs that already exist in the project
(condition survey result is mandatory; traffic and maintenance design
results are optional context) and emits a deduplicated, priority-sorted
list of ``TreatmentRecommendation``s with source-tagged CodeRefs.

Pure-Python, stateless. The row-level
``app.core.condition_survey.rehab_recommendations.recommend_rehab`` is
unchanged — Phase 12 sits *above* it, not in place of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from app.core.code_refs import CodeRef
from app.core.condition_survey import ConditionSurveyResult
from app.core.maintenance import (
    ColdMixResult,
    MicroSurfacingResult,
    OverlayResult,
)
from app.core.traffic import TrafficResult

from .rules import DEFAULT_RULES, Rule
from .treatments import (
    PLACEHOLDER_NOTE,
    RehabThresholds,
    TreatmentRecommendation,
    get_thresholds,
)


REFERENCES: Tuple[CodeRef, ...] = (
    CodeRef("IRC:82-1982", "",         "Maintenance of Bituminous Surfaces"),
    CodeRef("IRC:81-1997", "",         "BBD-based overlay strengthening"),
    CodeRef("IRC:115",     "",         "FWD-based structural evaluation / strengthening"),
    CodeRef("IRC:SP:81",   "",         "Slurry seal and microsurfacing"),
    CodeRef("IRC:SP:101",  "",         "Micro-surfacing specification"),
    CodeRef("IRC:19",      "",         "Bituminous surface dressing"),
    CodeRef("MoRTH-900",   "Sec. 3004", "Pothole patching"),
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RecommendationContext:
    """Bundle of survey-level inputs consumed by the rule list.

    ``condition`` is mandatory. The remaining fields are optional — when
    present, the rules can sharpen the recommendation (e.g. MSA gates
    slurry seal vs micro surfacing).
    """
    condition: ConditionSurveyResult
    traffic: Optional[TrafficResult] = None
    overlay_design: Optional[OverlayResult] = None
    cold_mix_design: Optional[ColdMixResult] = None
    micro_surfacing_design: Optional[MicroSurfacingResult] = None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RehabSynthesisResult:
    context_summary: str
    recommendations: Tuple[TreatmentRecommendation, ...]
    references: Tuple[CodeRef, ...] = REFERENCES
    is_placeholder: bool = True
    notes: str = PLACEHOLDER_NOTE


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def _summarize(ctx: RecommendationContext) -> str:
    pci = ctx.condition.pci_score
    cat = ctx.condition.condition_category
    parts = [f"PCI={pci:.2f} ({cat})",
             f"distress_records={len(ctx.condition.inputs.records)}"]
    if ctx.traffic is not None:
        parts.append(f"MSA={ctx.traffic.design_msa:.2f}")
        parts.append(f"traffic={ctx.traffic.traffic_category}")
    else:
        parts.append("traffic=unknown")
    return "; ".join(parts)


def _merge(existing: TreatmentRecommendation,
           new: TreatmentRecommendation) -> TreatmentRecommendation:
    """Combine two hits on the same category — reasons concatenated,
    triggers + refs unioned (order-preserving), priority = min."""
    merged_refs: list[CodeRef] = list(existing.references)
    for r in new.references:
        if r not in merged_refs:
            merged_refs.append(r)
    merged_trigs: list[str] = list(existing.triggers)
    for tr in new.triggers:
        if tr not in merged_trigs:
            merged_trigs.append(tr)
    return TreatmentRecommendation(
        category=existing.category,
        label=existing.label,
        reason=f"{existing.reason} {new.reason}".strip(),
        triggers=tuple(merged_trigs),
        priority=min(existing.priority, new.priority),
        references=tuple(merged_refs),
        next_module=existing.next_module or new.next_module,
        is_placeholder=True,
    )


def compute_rehab_recommendations(
    context: RecommendationContext,
    thresholds: Optional[RehabThresholds] = None,
    rules: Iterable[Rule] = DEFAULT_RULES,
) -> RehabSynthesisResult:
    """Apply ``rules`` to ``context`` and return a synthesised result.

    ``thresholds`` defaults to the active module-level set
    (``get_thresholds()``) so a calibration swap via
    :func:`set_thresholds` is honoured automatically. Callers can also
    pass a per-call override (useful for what-if analysis without
    mutating the module state).
    """
    t = thresholds if thresholds is not None else get_thresholds()
    by_cat: dict[str, TreatmentRecommendation] = {}
    for rule in rules:
        hit = rule(context, t)
        if hit is None:
            continue
        prev = by_cat.get(hit.category)
        by_cat[hit.category] = _merge(prev, hit) if prev is not None else hit
    ordered = sorted(
        by_cat.values(),
        key=lambda r: (r.priority, r.category),
    )
    return RehabSynthesisResult(
        context_summary=_summarize(context),
        recommendations=tuple(ordered),
        is_placeholder=True,
        notes=PLACEHOLDER_NOTE,
    )
