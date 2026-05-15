"""Placeholder rehab recommendation lookup.

PLACEHOLDER mapping of (distress_type, severity) -> treatment + IRC
reference. Future phases will calibrate these against the IRC:82
maintenance treatment matrix and any project-specific overrides.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from app.core.code_refs import CodeRef


@dataclass(frozen=True, slots=True)
class RehabRecommendation:
    distress_type: str
    severity: str
    treatment: str
    reference: CodeRef
    is_placeholder: bool = True


# Source tags reused from Phase 6 code registry.
_IRC82 = CodeRef("IRC:82-1982", "",          "Maintenance of Bituminous Surfaces")
_IRC82_53 = CodeRef("IRC:82-1982", "cl. 5.3", "Crack sealing")
_IRC82_54 = CodeRef("IRC:82-1982", "cl. 5.4", "Pothole patching")
_IRC82_55 = CodeRef("IRC:82-1982", "cl. 5.5", "Rut filling and overlay")
_IRC82_52 = CodeRef("IRC:82-1982", "cl. 5.2", "Surface dressing / seal coat")
_IRC82_56 = CodeRef("IRC:82-1982", "cl. 5.6", "Bleeding remediation")
_IRC81    = CodeRef("IRC:81-1997", "",        "BBD-based overlay design")
_MORTH3004 = CodeRef("MoRTH-900", "Sec. 3004", "Pothole patching specification")


# (distress_type, severity) -> (treatment, reference)
_RECOMMENDATIONS: Mapping[Tuple[str, str], Tuple[str, CodeRef]] = {
    ("cracking", "low"):    ("Crack sealing with bituminous emulsion", _IRC82_53),
    ("cracking", "medium"): ("Crack sealing + localised surface seal",  _IRC82_53),
    ("cracking", "high"):   ("Mill and overlay (BBD-based design)",     _IRC81),

    ("rutting", "low"):    ("Monitor; localised seal if depth grows",   _IRC82_55),
    ("rutting", "medium"): ("Partial-depth patching or thin overlay",   _IRC82_55),
    ("rutting", "high"):   ("Mill and overlay (BBD-based design)",      _IRC81),

    ("potholes", "low"):    ("Cold-mix patching",                       _MORTH3004),
    ("potholes", "medium"): ("Hot-mix patching to specification",       _IRC82_54),
    ("potholes", "high"):   ("Full-depth patching + binder/overlay",    _IRC82_54),

    ("ravelling", "low"):    ("Fog seal",                               _IRC82_52),
    ("ravelling", "medium"): ("Surface dressing",                       _IRC82_52),
    ("ravelling", "high"):   ("Thin bituminous overlay",                _IRC82_52),

    ("bleeding", "low"):    ("Sand blotting under hot weather",         _IRC82_56),
    ("bleeding", "medium"): ("Aggregate cover + roll",                  _IRC82_56),
    ("bleeding", "high"):   ("Mill and replace surface course",         _IRC82_56),

    ("patch_failures", "low"):    ("Re-seal patch perimeter",           _IRC82_54),
    ("patch_failures", "medium"): ("Re-patch with hot mix",             _IRC82_54),
    ("patch_failures", "high"):   ("Cut out and replace surface course", _IRC82_54),
}


def recommend_rehab(distress_type: str, severity: str) -> RehabRecommendation:
    """Look up the PLACEHOLDER treatment for a (type, severity) pair.

    Returns a RehabRecommendation with ``is_placeholder=True`` so the
    UI / report can flag it. Falls back to a generic IRC:82 entry if
    the pair is unknown.
    """
    key = (distress_type, severity)
    treatment, ref = _RECOMMENDATIONS.get(
        key,
        ("Engineer to specify — no preset for this (type, severity) pair", _IRC82),
    )
    return RehabRecommendation(
        distress_type=distress_type,
        severity=severity,
        treatment=treatment,
        reference=ref,
        is_placeholder=True,
    )
