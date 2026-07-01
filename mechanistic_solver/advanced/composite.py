"""Composite pavement models, asphalt overlays, and interface shear friction slip relations."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class OverlayDesign:
    """Asphalt overlay design parameters on top of existing cracked rigid pavements."""
    existing_slab_thickness_mm: float
    existing_elastic_modulus_mpa: float
    design_traffic_msa: float
    deflection_rebound_mm: float = 1.2


class CompositePavementModel:
    """Calculates rigid base structural response, asphalt overlay thickness, and slip friction factors."""

    @staticmethod
    def get_overlay_thickness_recommendation(design: OverlayDesign) -> float:
        """Estimate recommended asphalt overlay thickness using the Asphalt Institute (AI) deflection method.

        Formula: t_ol = 250 * log10( D_rebound / D_allowable )
        where D_allowable = 0.5 mm for typical heavy traffic.
        Reference: Asphalt Institute MS-17 (Asphalt Overlays for Highway and Street Pavements).
        """
        d_allow = 0.50
        ratio = max(1.0, design.deflection_rebound_mm / d_allow)
        t_ol = 250.0 * math.log10(ratio)
        return max(40.0, t_ol)  # Never recommend less than a standard 40mm course

    @staticmethod
    def get_rigid_slab_bending_stress(
        wheel_load_kn: float,
        slab_thickness_mm: float,
        slab_modulus_mpa: float,
        subgrade_reaction_k_mpa_m: float = 48.0
    ) -> float:
        """Compute the tensile bending stress at the bottom of the rigid concrete slab under overlay.

        Formula: sigma = 3 * P * (1 + nu) / (2 * pi * h^2) * (ln(l / b) + 0.617)
        where:
          l = radius of relative stiffness = ( (E * h^3) / (12 * (1 - nu^2) * k) )^0.25
        Reference: Westergaard, H.M. (1926). Stresses in Concrete Pavements by Runways.
        """
        h_m = slab_thickness_mm / 1000.0
        p_n = wheel_load_kn * 1000.0
        nu = 0.15  # standard concrete poisson
        
        # Westergaard radius of relative stiffness (l)
        l_stiffness = ((slab_modulus_mpa * 1e6 * h_m**3) / (12.0 * (1.0 - nu**2) * subgrade_reaction_k_mpa_m * 1e6)) ** 0.25
        
        # Equivalent radius of contact area (a), assuming standard dual contact
        a_radius = 0.15  # 150mm
        if a_radius >= 1.724 * h_m:
            b_radius = a_radius
        else:
            b_radius = math.sqrt(1.6 * a_radius**2 + h_m**2) - 0.675 * h_m
            
        if b_radius <= 0.0:
            b_radius = 1e-4
            
        # Westergaard edge loading stress formula (converted to MPa)
        stress_pa = (3.0 * p_n * (1.0 + nu)) / (2.0 * math.pi * h_m**2) * (math.log(l_stiffness / b_radius) + 0.617)
        return stress_pa / 1e6

    @staticmethod
    def get_interface_slip_factor(shear_stress_mpa: float, slip_parameter_alpha: float) -> float:
        """Calculate the slip displacement at the overlay-slab interface.

        Formula: delta_u = alpha * tau
        where alpha represents interface compliance (0 for fully bonded, higher values represent partial bonding).
        Reference: Goodman, R.E., et al. (1968). A Model for the Behavior of Jointed Rock.
        """
        return slip_parameter_alpha * shear_stress_mpa
