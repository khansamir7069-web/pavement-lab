"""Phase-14 strain-extraction helpers.

Pull the two design-critical strains from a Phase-13
``MechanisticResult`` for the fatigue and rutting checks:

  * tensile strain at the bottom of the bituminous-bound stack
    (``"bottom_of_BT"``)         -> fatigue
  * vertical compressive strain at the top of the subgrade
    (``"top_of_subgrade"``)     -> rutting

The Phase-13 ``default_evaluation_points`` helper labels its two points
exactly so. When a caller supplies custom evaluation points without
labels, this module falls back to using the *first* point for fatigue
and the *last* point for rutting AND emits a non-empty ``warning``
string so the caller can propagate it into the result ``notes`` field
— per Phase-14 decision: never silently substitute without traceability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.iitpave import MechanisticResult


LABEL_FATIGUE: str = "bottom_of_BT"
LABEL_RUTTING: str = "top_of_subgrade"


@dataclass(frozen=True, slots=True)
class StrainExtraction:
    """One extracted strain plus a traceability trail.

    ``value_microstrain`` is None when nothing was extractable; the
    engine treats that as a refusal trigger.
    """
    value_microstrain: Optional[float]
    point_label: str
    fallback_used: bool
    warning: str               # empty when no fallback was needed


def _point_by_label(mech_result: MechanisticResult, label: str):
    """Return the first PointResult whose stored EvaluationPoint label
    matches. PointResult itself does NOT carry the label, but
    MechanisticResult.point_results preserves the supplied order so the
    engine resolves labels via the caller (see ``extract_*``)."""
    # PointResult intentionally has no label field — keeping that
    # surface frozen per Phase-13 contract. The engine therefore
    # resolves labels by matching against the original input points.
    return None  # never used directly; kept for explicit documentation


def extract_fatigue_strain(
    mech_result: MechanisticResult,
    *,
    fatigue_label: str = LABEL_FATIGUE,
    point_labels: Optional[tuple[str, ...]] = None,
) -> StrainExtraction:
    """Find the tensile strain at the bottom of the BT stack.

    Resolution order:
      1. If ``point_labels`` is supplied (one entry per point in
         ``mech_result.point_results``) and contains ``fatigue_label``,
         use the matching point's ``epsilon_t_microstrain``.
      2. Fallback: use the FIRST point and emit a warning.
    """
    pts = mech_result.point_results
    if not pts:
        return StrainExtraction(
            value_microstrain=None,
            point_label="",
            fallback_used=False,
            warning="No evaluation points present in MechanisticResult.",
        )
    if point_labels and len(point_labels) == len(pts):
        for label, pt in zip(point_labels, pts):
            if label == fatigue_label:
                return StrainExtraction(
                    value_microstrain=float(pt.epsilon_t_microstrain),
                    point_label=label,
                    fallback_used=False,
                    warning="",
                )
        warning = (
            f"No evaluation point labelled {fatigue_label!r}; "
            f"falling back to first point (label={point_labels[0]!r}). "
            "Strain provenance must be confirmed before adopting verdict."
        )
        return StrainExtraction(
            value_microstrain=float(pts[0].epsilon_t_microstrain),
            point_label=point_labels[0],
            fallback_used=True,
            warning=warning,
        )
    # Fallback: no labels supplied -> use first point.
    return StrainExtraction(
        value_microstrain=float(pts[0].epsilon_t_microstrain),
        point_label="(unlabelled[0])",
        fallback_used=True,
        warning=(
            "No point labels supplied to extract_fatigue_strain; "
            "falling back to first point. Strain provenance must be "
            "confirmed before adopting verdict."
        ),
    )


def extract_rutting_strain(
    mech_result: MechanisticResult,
    *,
    rutting_label: str = LABEL_RUTTING,
    point_labels: Optional[tuple[str, ...]] = None,
) -> StrainExtraction:
    """Find the vertical compressive strain at the top of the subgrade."""
    pts = mech_result.point_results
    if not pts:
        return StrainExtraction(
            value_microstrain=None,
            point_label="",
            fallback_used=False,
            warning="No evaluation points present in MechanisticResult.",
        )
    if point_labels and len(point_labels) == len(pts):
        for label, pt in zip(point_labels, pts):
            if label == rutting_label:
                return StrainExtraction(
                    value_microstrain=float(pt.epsilon_z_microstrain),
                    point_label=label,
                    fallback_used=False,
                    warning="",
                )
        warning = (
            f"No evaluation point labelled {rutting_label!r}; "
            f"falling back to last point (label={point_labels[-1]!r}). "
            "Strain provenance must be confirmed before adopting verdict."
        )
        return StrainExtraction(
            value_microstrain=float(pts[-1].epsilon_z_microstrain),
            point_label=point_labels[-1],
            fallback_used=True,
            warning=warning,
        )
    # Fallback: no labels supplied -> use last point.
    return StrainExtraction(
        value_microstrain=float(pts[-1].epsilon_z_microstrain),
        point_label="(unlabelled[-1])",
        fallback_used=True,
        warning=(
            "No point labels supplied to extract_rutting_strain; "
            "falling back to last point. Strain provenance must be "
            "confirmed before adopting verdict."
        ),
    )
