"""Engineering Intelligence Checker for pavement design validation.

Implements structural layer compatibility checks, modular ratio screening,
and computes the Engineering Screening Score (0-100).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, List
from .structural_design import PavementLayer

@dataclass(frozen=True, slots=True)
class IntelligenceResult:
    health_score: float                  # Engineering Screening Score
    risk_level: str                      # "Healthy" | "Acceptable" | "Needs Review" | "High Risk"
    warnings: Tuple[str, ...]
    review_notes: Tuple[str, ...]


def detect_layer_type(layer: PavementLayer) -> str:
    """Classify the pavement layer based on its name and material properties."""
    name_lower = layer.name.lower()
    mat_lower = (layer.material or "").lower()
    if "ctb" in name_lower or "ctb" in mat_lower or "cement treated base" in name_lower:
        return "ctb"
    if "cts" in name_lower or "cts" in mat_lower or "cement treated sub-base" in name_lower or "cement treated subbase" in name_lower:
        return "cts"
    if "gsb" in name_lower or "gsb" in mat_lower or "granular sub-base" in name_lower or "granular subbase" in name_lower:
        return "gsb"
    if "wmm" in name_lower or "wmm" in mat_lower or "wet mix macadam" in name_lower or "granular base" in name_lower or "crushed stone" in name_lower:
        return "granular_base"
    if any(x in name_lower or x in mat_lower for x in ("bc", "dbm", "bituminous", "concrete", "macadam", "cover", "asphalt")):
        return "bituminous"
    return "unknown"


def get_material_tier(layer_type: str) -> int:
    """Get the relative structural quality tier of the layer material."""
    tiers = {
        "bituminous": 5,
        "ctb": 4,
        "cts": 3,
        "granular_base": 2,
        "gsb": 1,
        "unknown": 0,
    }
    return tiers.get(layer_type, 0)


def check_pavement_intelligence(
    composition: Tuple[PavementLayer, ...] | List[PavementLayer],
    subgrade_mr_mpa: float | None = None,
) -> IntelligenceResult:
    """Perform static engineering compatibility checks and calculate the screening score."""
    warnings_list: list[str] = []
    notes_list: list[str] = []
    score = 100.0

    layers = list(composition)

    # 1. Missing Layer Data
    if not layers:
        warnings_list.append("Engineering review required: No pavement layers defined in composition.")
        return IntelligenceResult(
            health_score=0.0,
            risk_level="High Risk",
            warnings=tuple(warnings_list),
            review_notes=("Ensure at least one structural layer is configured.",),
        )

    # 2. Loop through each layer for individual parameter checks
    for idx, ly in enumerate(layers):
        l_type = detect_layer_type(ly)

        # Modulus presence check
        if ly.modulus_mpa is None or ly.modulus_mpa <= 0:
            warnings_list.append(
                f"Engineering review required: Missing modulus for layer '{ly.name}'."
            )
            score -= 15.0
            continue

        thick = ly.thickness_mm
        mod = ly.modulus_mpa

        # Thickness screening rules
        if l_type == "bituminous":
            if "concrete" in ly.name.lower() or "bc" in ly.name.lower():
                if thick < 25.0 or thick > 60.0:
                    warnings_list.append(
                        f"Engineering review required: Unusual BC layer thickness ({thick:.0f} mm) is outside typical screening range of 25 to 60 mm."
                    )
                    score -= 5.0
            elif "macadam" in ly.name.lower() or "dbm" in ly.name.lower():
                if thick < 50.0 or thick > 200.0:
                    warnings_list.append(
                        f"Engineering review required: Unusual DBM layer thickness ({thick:.0f} mm) is outside typical screening range of 50 to 200 mm."
                    )
                    score -= 5.0
        elif l_type == "granular_base":
            if thick < 100.0 or thick > 300.0:
                warnings_list.append(
                    f"Engineering review required: Unusual Granular Base thickness ({thick:.0f} mm) is outside typical screening range of 100 to 300 mm."
                )
                score -= 5.0
        elif l_type == "gsb":
            if thick < 100.0 or thick > 450.0:
                warnings_list.append(
                    f"Engineering review required: Unusual GSB layer thickness ({thick:.0f} mm) is outside typical screening range of 100 to 450 mm."
                )
                score -= 5.0
        elif l_type in ("ctb", "cts"):
            if thick < 100.0:
                warnings_list.append(
                    f"Engineering review required: Stabilized layer '{ly.name}' thickness ({thick:.0f} mm) is below the minimum recommended structural lift of 100 mm."
                )
                score -= 15.0
            elif thick > 250.0:
                warnings_list.append(
                    f"Engineering review required: Stabilized layer '{ly.name}' thickness ({thick:.0f} mm) exceeds the typical 250 mm single-lift construction limit."
                )
                score -= 10.0

        # Poisson's ratio check if available
        if hasattr(ly, "poisson") and ly.poisson is not None:
            poisson = ly.poisson
            if poisson <= 0.05 or poisson >= 0.49:
                warnings_list.append(
                    f"Engineering review required: Physically invalid Poisson's ratio ({poisson:.2f}) for layer '{ly.name}'."
                )
                score -= 20.0
            elif l_type in ("ctb", "cts"):
                if poisson < 0.15 or poisson > 0.35:
                    warnings_list.append(
                        f"Engineering review required: Non-standard Poisson's ratio ({poisson:.2f}) for stabilized layer '{ly.name}' (typical range: 0.15 to 0.35)."
                    )
                    score -= 10.0
            elif l_type in ("bituminous", "granular_base", "gsb"):
                if poisson < 0.30 or poisson > 0.40:
                    warnings_list.append(
                        f"Engineering review required: Non-standard Poisson's ratio ({poisson:.2f}) for layer '{ly.name}' (typical range: 0.30 to 0.40)."
                    )
                    score -= 5.0

    # 3. Material Placement (Tiers) Check
    for i in range(len(layers) - 1):
        upper_type = detect_layer_type(layers[i])
        lower_type = detect_layer_type(layers[i+1])
        upper_tier = get_material_tier(upper_type)
        lower_tier = get_material_tier(lower_type)

        if upper_tier != 0 and lower_tier != 0 and upper_tier < lower_tier:
            warnings_list.append(
                f"Engineering review required: Material placement anomaly. Lower-tier material '{layers[i].name}' (Tier {upper_tier}) is placed above higher-tier material '{layers[i+1].name}' (Tier {lower_tier})."
            )
            score -= 20.0

    # 4. Adjacent Layer Modular Ratios & Compatibility Checks
    for i in range(len(layers) - 1):
        ly_upper = layers[i]
        ly_lower = layers[i+1]

        if (ly_upper.modulus_mpa is None or ly_upper.modulus_mpa <= 0 or
            ly_lower.modulus_mpa is None or ly_lower.modulus_mpa <= 0):
            continue

        e_upper = ly_upper.modulus_mpa
        e_lower = ly_lower.modulus_mpa
        ratio = e_upper / e_lower
        type_upper = detect_layer_type(ly_upper)
        type_lower = detect_layer_type(ly_lower)

        # Granular base / sub-base compatibility
        if type_upper == "granular_base" and type_lower == "gsb":
            if ratio < 1.0 or ratio > 4.0:
                warnings_list.append(
                    f"Engineering review required: Base-to-subbase modulus ratio ({ratio:.1f}) is outside recommended compatibility screening range (maximum 4.0)."
                )
                score -= 15.0

        # CTB / CTS compatibility
        elif type_upper == "ctb" and type_lower == "cts":
            if ratio > 5.0:
                warnings_list.append(
                    f"Engineering review required: CTB-to-CTS modulus ratio ({ratio:.1f}) is outside recommended compatibility screening range (maximum 5.0)."
                )
                score -= 15.0

        # Very stiff stabilized layer over weak support
        if type_upper in ("ctb", "cts") and type_lower in ("gsb", "unknown"):
            if e_lower < 500.0:
                warnings_list.append(
                    f"Engineering review required: Very stiff stabilized layer '{ly_upper.name}' is placed directly over weak support '{ly_lower.name}' ({e_lower:.0f} MPa < 500 MPa). Potential risk of cracking due to stiffness mismatch."
                )
                score -= 20.0

        # General excessive modular ratio (excluding bituminous cover over CTB/CTS)
        is_cover_over_stabilized = (type_upper == "bituminous" and type_lower in ("ctb", "cts"))
        if ratio > 10.0 and not is_cover_over_stabilized:
            warnings_list.append(
                f"Engineering review required: Excessive modular ratio between adjacent layers ({ly_upper.name} to {ly_lower.name} ratio = {ratio:.1f} > 10.0). Risk of high tensile strain at interface."
            )
            score -= 15.0

        # Stiffness inversion check (lower stiffer than upper)
        if e_lower > 1.3 * e_upper and not is_cover_over_stabilized:
            warnings_list.append(
                f"Engineering review required: Stiffness inversion detected. Lower layer '{ly_lower.name}' ({e_lower:.0f} MPa) is stiffer than upper layer '{ly_upper.name}' ({e_upper:.0f} MPa)."
            )
            score -= 15.0

    # 5. Subgrade Compatibility Checks
    if subgrade_mr_mpa is not None and subgrade_mr_mpa > 0:
        # Bottom layer relative to subgrade
        ly_bottom = layers[-1]
        if ly_bottom.modulus_mpa is not None and ly_bottom.modulus_mpa > 0:
            e_bottom = ly_bottom.modulus_mpa
            ratio_sub = e_bottom / subgrade_mr_mpa
            if ratio_sub > 4.0:
                warnings_list.append(
                    f"Engineering review required: Bottom pavement layer '{ly_bottom.name}' is too stiff relative to subgrade support (ratio {ratio_sub:.1f} > 4.0)."
                )
                score -= 15.0

            # Very stiff layer over subgrade support
            type_bottom = detect_layer_type(ly_bottom)
            if type_bottom in ("ctb", "cts") and subgrade_mr_mpa < 100.0:
                warnings_list.append(
                    f"Engineering review required: Very stiff stabilized layer '{ly_bottom.name}' is placed directly over subgrade support ({subgrade_mr_mpa:.0f} MPa < 100 MPa). Potential risk of cracking due to stiffness mismatch."
                )
                score -= 20.0

        # Weak subgrade with extremely stiff upper layer
        if subgrade_mr_mpa < 40.0:
            has_high_stiffness_upper = any(
                ly.modulus_mpa is not None and ly.modulus_mpa >= 5000.0 for ly in layers
            )
            if has_high_stiffness_upper:
                warnings_list.append(
                    f"Engineering review required: High stiffness layer placed over very weak subgrade support ({subgrade_mr_mpa:.0f} MPa). Risk of subgrade rutting."
                )
                score -= 20.0

    # Floor score at 0.0
    score = max(0.0, score)

    # 6. Map Risk Level & Notes
    if score >= 90.0:
        risk = "Healthy"
        notes_list.append("Pavement design shows excellent layer compatibility.")
    elif score >= 75.0:
        risk = "Acceptable with minor review"
        notes_list.append("Layer stack is acceptable. Minor review of non-standard modular ratios or thicknesses suggested.")
    elif score >= 50.0:
        risk = "Needs engineering review"
        notes_list.append("Design requires engineering review. Layer modular ratios or thicknesses deviate from typical screening limits.")
    else:
        risk = "High-risk design"
        notes_list.append("High-risk design flagged. Structural layer arrangement shows critical stiffness mismatches or material placement anomalies.")

    # Always add general guidelines note
    notes_list.append("Review is based on static pavement guidelines. Final designs must be mechanistically validated in IITPAVE.")

    return IntelligenceResult(
        health_score=score,
        risk_level=risk,
        warnings=tuple(warnings_list),
        review_notes=tuple(notes_list),
    )
