"""Modular rule set — Phase 12.

Each rule is a callable ``(ctx, thresholds) -> Optional[TreatmentRecommendation]``.
The default ``DEFAULT_RULES`` list below covers all eight treatment
categories. New rules can be appended via the ``rules=`` argument of
:func:`compute_rehab_recommendations` without editing this file.

All triggering numerics read from the active ``RehabThresholds`` so the
calibration story stays in one place. Every emitted recommendation
carries ``is_placeholder=True``.
"""
from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from .treatments import (
    CATEGORY_LABELS,
    CATEGORY_NEXT_MODULE,
    CATEGORY_PRIORITY,
    CR_IRC19,
    CR_IRC81,
    CR_IRC82,
    CR_IRC82_52,
    CR_IRC82_53,
    CR_IRC82_54,
    CR_IRC115,
    CR_IRC_SP_81,
    CR_IRC_SP_101,
    CR_MORTH_3004,
    RehabThresholds,
    TC_CRACK_SEALING,
    TC_MICRO_SURFACING,
    TC_OVERLAY,
    TC_POTHOLE_PATCHING,
    TC_RECONSTRUCTION,
    TC_ROUTINE_MAINTENANCE,
    TC_SLURRY_SEAL,
    TC_SURFACE_TREATMENT,
    TreatmentRecommendation,
)

if TYPE_CHECKING:
    from .engine import RecommendationContext


Rule = Callable[
    ["RecommendationContext", RehabThresholds],
    Optional[TreatmentRecommendation],
]


# ---------------------------------------------------------------------------
# Helpers (cheap aggregations over the condition result)
# ---------------------------------------------------------------------------

def _records(ctx: "RecommendationContext"):
    return ctx.condition.inputs.records or ()


def _count_distress(ctx, code: str, *severities: str) -> int:
    sset = set(severities) if severities else None
    return sum(
        1 for r in _records(ctx)
        if r.distress_type == code and (sset is None or r.severity in sset)
    )


def _any_high_severity(ctx, *codes: str) -> bool:
    cset = set(codes) if codes else None
    return any(
        r.severity == "high" and (cset is None or r.distress_type in cset)
        for r in _records(ctx)
    )


def _sum_extent_area(ctx, code: str) -> float:
    return sum(
        r.area_m2 for r in _records(ctx)
        if r.distress_type == code
    )


def _pci(ctx) -> float:
    return float(ctx.condition.pci_score)


def _msa(ctx) -> Optional[float]:
    if ctx.traffic is None:
        return None
    return float(ctx.traffic.design_msa)


def _build(category: str, *, reason: str, triggers: tuple[str, ...],
           refs: tuple) -> TreatmentRecommendation:
    return TreatmentRecommendation(
        category=category,
        label=CATEGORY_LABELS[category],
        reason=reason,
        triggers=tuple(triggers),
        priority=CATEGORY_PRIORITY[category],
        references=tuple(refs),
        next_module=CATEGORY_NEXT_MODULE[category],
        is_placeholder=True,
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule_routine_maintenance(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    if pci < t.pci_excellent_min:
        return None
    if _any_high_severity(ctx):
        return None
    return _build(
        TC_ROUTINE_MAINTENANCE,
        reason=(f"PCI {pci:.1f} >= {t.pci_excellent_min:g} (Excellent) and "
                "no high-severity distress observed."),
        triggers=(f"PCI={pci:.1f}", "no_high_severity"),
        refs=(CR_IRC82,),
    )


def rule_crack_sealing(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    if pci < t.pci_fair_min:
        return None
    # Low/medium cracking only — high-severity cracking is handled by overlay.
    cracks = _count_distress(ctx, "cracking", "low", "medium")
    if cracks == 0:
        return None
    return _build(
        TC_CRACK_SEALING,
        reason=(f"{cracks} cracking record(s) of low/medium severity with "
                f"PCI {pci:.1f} >= {t.pci_fair_min:g}."),
        triggers=(f"cracking_lm={cracks}", f"PCI={pci:.1f}"),
        refs=(CR_IRC82_53, CR_IRC82),
    )


def rule_pothole_patching(ctx, t: RehabThresholds):
    n = _count_distress(ctx, "potholes")
    if n == 0:
        return None
    return _build(
        TC_POTHOLE_PATCHING,
        reason=f"{n} pothole record(s) detected — safety priority.",
        triggers=(f"potholes={n}",),
        refs=(CR_MORTH_3004, CR_IRC82_54),
    )


def rule_surface_treatment(ctx, t: RehabThresholds):
    ravel_lm = _count_distress(ctx, "ravelling", "low", "medium")
    bleed_lm = _count_distress(ctx, "bleeding", "low", "medium")
    if ravel_lm == 0 and bleed_lm == 0:
        return None
    trigs: list[str] = []
    if ravel_lm:
        trigs.append(f"ravelling_lm={ravel_lm}")
    if bleed_lm:
        trigs.append(f"bleeding_lm={bleed_lm}")
    return _build(
        TC_SURFACE_TREATMENT,
        reason=("Surface-course distress (ravelling/bleeding low-medium) "
                "observed — surface treatment indicated."),
        triggers=tuple(trigs),
        refs=(CR_IRC19, CR_IRC82_52),
    )


def rule_slurry_seal(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    if not (t.pci_fair_min <= pci < t.pci_good_min):
        return None
    if _any_high_severity(ctx, "rutting"):
        return None
    msa = _msa(ctx)
    if msa is not None and msa > t.msa_low_max:
        return None
    trigs = [f"PCI={pci:.1f}"]
    trigs.append(f"MSA<={t.msa_low_max:g}" if msa is not None else "MSA=unknown")
    return _build(
        TC_SLURRY_SEAL,
        reason=(f"Fair PCI {pci:.1f} with "
                f"{'MSA ' + format(msa, '.2f') if msa is not None else 'no traffic data'}; "
                "preventive slurry seal indicated."),
        triggers=tuple(trigs),
        refs=(CR_IRC_SP_81,),
    )


def rule_micro_surfacing(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    if not (t.pci_fair_min <= pci < t.pci_good_min):
        return None
    msa = _msa(ctx)
    if msa is None or not (t.msa_low_max < msa <= t.msa_mid_max):
        return None
    return _build(
        TC_MICRO_SURFACING,
        reason=(f"Fair PCI {pci:.1f} with mid-range MSA {msa:.2f} "
                f"(in ({t.msa_low_max:g}, {t.msa_mid_max:g}]); "
                "micro-surfacing indicated."),
        triggers=(f"PCI={pci:.1f}", f"MSA={msa:.2f}"),
        refs=(CR_IRC_SP_101, CR_IRC_SP_81),
    )


def rule_overlay(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    trigs: list[str] = []
    reasons: list[str] = []
    if t.pci_poor_min <= pci < t.pci_fair_min:
        trigs.append(f"PCI={pci:.1f}")
        reasons.append(f"Poor PCI {pci:.1f}")
    if _any_high_severity(ctx, "rutting", "cracking"):
        trigs.append("hi_sev_rutting_or_cracking")
        reasons.append("high-severity rutting or cracking present")
    msa = _msa(ctx)
    if msa is not None and msa > t.msa_mid_max:
        trigs.append(f"MSA={msa:.2f}>{t.msa_mid_max:g}")
        reasons.append(f"heavy traffic MSA {msa:.2f} > {t.msa_mid_max:g}")
    if not trigs:
        return None
    return _build(
        TC_OVERLAY,
        reason=("Overlay / strengthening indicated: " + "; ".join(reasons) +
                "."),
        triggers=tuple(trigs),
        refs=(CR_IRC81, CR_IRC115),
    )


def rule_reconstruction(ctx, t: RehabThresholds):
    pci = _pci(ctx)
    if pci >= t.pci_poor_min:
        return None
    return _build(
        TC_RECONSTRUCTION,
        reason=(f"PCI {pci:.1f} < {t.pci_poor_min:g} — pavement is below the "
                "rehabilitation threshold. Engineer confirmation required "
                "before adopting reconstruction (PLACEHOLDER trigger)."),
        triggers=(f"PCI={pci:.1f}", "below_pci_poor_min"),
        refs=(CR_IRC115,),
    )


DEFAULT_RULES: tuple[Rule, ...] = (
    rule_routine_maintenance,
    rule_crack_sealing,
    rule_pothole_patching,
    rule_surface_treatment,
    rule_slurry_seal,
    rule_micro_surfacing,
    rule_overlay,
    rule_reconstruction,
)
